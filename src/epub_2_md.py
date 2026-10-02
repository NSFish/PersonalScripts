#!/usr/bin/env python3
"""扫描版 EPUB → Markdown（macOS Vision OCR + 按 TOC 切章 + 表格/插图保留原图）。

适用：EPUB 正文全是扫描图（XHTML 里只有 <img>），没有文本层。流程：

1. 解包后按 spine 顺序读 XHTML，按文档流里 <img> 出现的先后确定阅读顺序
   （扫描件的图片文件名往往是乱的，不能按文件名排）；
2. 用 toc.ncx 里的锚点把页面归属到章、节；
3. 逐页跑 Vision OCR（保留 bounding box），用行坐标还原段落、剔除页眉页脚页码；
4. 识别「表 x-y」「图 x-y」，用行墨迹的空白带找出整块区域，裁下原图放进 assets/，
   该区域的 OCR 文本降级到 <details> 里备查（表格数字不可靠，必须以图为准）；
5. 按章输出 md，每页带页码锚点，便于回查原图。

OCR 结果按图片名缓存在 <输出目录>/.ocr_cache/，重跑不会重复识别。
"""
import argparse
import json
import posixpath
import re
import statistics
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from lxml import etree
from PIL import Image
from Foundation import NSURL
import Quartz
import Vision

CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}
NCX_NS = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}

REC_LANGS = ["zh-Hans", "zh-Hant", "en-US"]

# 文档流里的图片与锚点，按出现顺序
TAG_RE = re.compile(
    r"""<img\b[^>]*?src=["']([^"']+)["']"""
    r"""|<(?:span|a|p|div|h[1-6])\b[^>]*?id=["']([^"']+)["']""",
    re.I | re.S,
)
CAPTION_RE = re.compile(r"^[表图]\s*[0-9一二三四五六七八九十]{1,3}\s*[-－—–]\s*[0-9]{1,3}")
CONT_RE = re.compile(r"^续表$")          # 跨页表格的续表页，正文没有图题可锚
CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+章")
SECTION_RE = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+节")
PAGE_NUM_RE = re.compile(r"^[0-9]{1,4}$")
BULLET_RE = re.compile(r"^(?:[（(]\s*\d{1,2}\s*[）)]|\d{1,2}\s*[、.．]|[①-⑳])")
CONTINUE_PUNCT = "。，、；：？！）》】”’…—·"
CN_DIGITS = "零一二三四五六七八九"

HEAD_BAND = 0.09      # 页眉判定：行底边在页高 9% 以内
FOOT_BAND = 0.92      # 页脚判定：行顶边在页高 92% 以外
BLANK_ROW = 0.005     # 单行墨迹占比低于此值算空白行
INK_LEVEL = 170       # 灰度低于此值算墨迹


# ---------------------------------------------------------------- EPUB 解析

def read_epub(epub_path):
    """返回 (ZipFile, docs, toc, title)。docs=[(zip 内路径, 文本)]，toc=[{title,doc,frag}]。"""
    zf = zipfile.ZipFile(epub_path)
    container = etree.fromstring(zf.read("META-INF/container.xml"))
    opf_path = container.xpath("//c:rootfile/@full-path", namespaces=CONTAINER_NS)[0]
    opf = etree.fromstring(zf.read(opf_path))

    title = (opf.xpath("//*[local-name()='title']/text()") or [Path(epub_path).stem])[0]
    base = posixpath.dirname(opf_path)

    manifest = {}
    for item in opf.xpath("//opf:manifest/opf:item", namespaces=OPF_NS):
        manifest[item.get("id")] = item

    docs = []
    for itemref in opf.xpath("//opf:spine/opf:itemref", namespaces=OPF_NS):
        item = manifest.get(itemref.get("idref"))
        if item is None:
            continue
        href = item.get("href") or ""
        if not href.lower().endswith((".html", ".xhtml", ".htm")):
            continue
        full = posixpath.normpath(posixpath.join(base, href))
        try:
            docs.append((full, zf.read(full).decode("utf-8", "ignore")))
        except KeyError:
            continue

    toc = []
    spine = opf.xpath("//opf:spine", namespaces=OPF_NS)
    toc_id = spine[0].get("toc") if spine else None
    if toc_id and toc_id in manifest:
        ncx_path = posixpath.normpath(posixpath.join(base, manifest[toc_id].get("href")))
        toc = parse_ncx(zf.read(ncx_path), posixpath.dirname(ncx_path))
    if not toc and docs:
        toc = [{"title": title, "doc": docs[0][0], "frag": ""}]
    return zf, docs, toc, title


def parse_ncx(data, ncx_dir):
    """toc.ncx → [{title, doc, frag}]，保持文档顺序。"""
    root = etree.fromstring(data)
    out = []
    for np in root.xpath("//ncx:navPoint", namespaces=NCX_NS):
        label = "".join(np.xpath("./ncx:navLabel/ncx:text/text()", namespaces=NCX_NS)).strip()
        src = (np.xpath("./ncx:content/@src", namespaces=NCX_NS) or [""])[0]
        if not label or not src:
            continue
        path, _, frag = src.partition("#")
        doc = posixpath.normpath(posixpath.join(ncx_dir, path)) if path else ""
        out.append({"title": label, "doc": doc, "frag": frag, "pages": []})
    return out


def build_stream(docs):
    """文档流 → [('img', doc, zip 内图片路径) | ('anchor', doc, id)]。"""
    stream = []
    for doc, text in docs:
        for match in TAG_RE.finditer(text):
            src, anchor = match.group(1), match.group(2)
            if src:
                stream.append(("img", doc, posixpath.normpath(
                    posixpath.join(posixpath.dirname(doc), src))))
            else:
                stream.append(("anchor", doc, anchor))
    return stream


def assign_pages(stream, toc):
    """某条目的页面 = 从它的锚点到下一条目锚点之间出现的图（图片文件名顺序不可信）。"""
    anchor_at, doc_start = {}, {}
    for i, (kind, doc, val) in enumerate(stream):
        if kind == "anchor":
            anchor_at.setdefault((doc, val), i)
        doc_start.setdefault(doc, i)

    starts = []
    for entry in toc:
        key = (entry["doc"], entry["frag"])
        if entry["frag"] and key in anchor_at:
            starts.append(anchor_at[key])
        else:
            starts.append(doc_start.get(entry["doc"], 0))

    pages = []
    for i, entry in enumerate(toc):
        end = starts[i + 1] if i + 1 < len(toc) else len(stream)
        entry["pages"] = [val for kind, _doc, val in stream[starts[i]:end] if kind == "img"]
        pages.extend(entry["pages"])
    return pages


# ------------------------------------------------------------------- OCR

def cg_image_from_path(path):
    url = NSURL.fileURLWithPath_(str(path))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        return None
    return Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)


def ocr_image(cg_image):
    """Vision OCR → [{text,x,y,w,h}]（归一化坐标，原点在左下）；失败返回 None。"""
    request = Vision.VNRecognizeTextRequest.new()
    request.setRecognitionLanguages_(REC_LANGS)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    ok, error = handler.performRequests_error_([request], None)
    if not ok or error:
        return None
    out = []
    for obs in request.results() or []:
        text = (obs.text() or "").strip()
        if not text:
            continue
        box = obs.boundingBox()
        try:
            (x, y), (w, h) = box
        except (TypeError, ValueError):
            x, y, w, h = box.origin.x, box.origin.y, box.size.width, box.size.height
        out.append({"text": text, "x": float(x), "y": float(y),
                    "w": float(w), "h": float(h)})
    return out


def ocr_page_cached(path, member, cache_dir):
    """带缓存地 OCR 一张图 → (lines, 宽, 高)。"""
    cache_file = cache_dir / (re.sub(r"[^0-9A-Za-z._-]", "_", member) + ".json")
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if data.get("lines") is not None:
            return data["lines"], data["width"], data["height"]
    cg = cg_image_from_path(path)
    if cg is None:
        return None, 0, 0
    width, height = Quartz.CGImageGetWidth(cg), Quartz.CGImageGetHeight(cg)
    lines = ocr_image(cg)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(
        {"width": width, "height": height, "lines": lines}, ensure_ascii=False),
        encoding="utf-8")
    return lines, width, height


def to_pixels(lines, img_w, img_h):
    """归一化坐标 → 像素坐标（top 从页顶算），并补上字宽字高。"""
    out = []
    for line in lines:
        left = line["x"] * img_w
        right = (line["x"] + line["w"]) * img_w
        top = (1 - line["y"] - line["h"]) * img_h
        bottom = (1 - line["y"]) * img_h
        chars = len(re.sub(r"\s", "", line["text"]))
        out.append({
            "text": line["text"],
            "left": left, "right": right, "top": top, "bottom": bottom,
            "cy": (top + bottom) / 2,
            "chars": chars,
            "char_w": (right - left) / max(chars, 1),
            "char_h": bottom - top,
        })
    return out


# ------------------------------------------------------------ 版面还原

def running_head_of(pages):
    """在页顶带里出现得足够频繁的短文本＝书眉（如书名）。"""
    counts = {}
    for page in pages:
        for line in page["lines"]:
            if line["bottom"] <= HEAD_BAND * page["h"] and 1 <= line["chars"] <= 12:
                if CHAPTER_RE.match(line["text"]) or SECTION_RE.match(line["text"]):
                    continue
                counts[line["text"]] = counts.get(line["text"], 0) + 1
    if not counts:
        return None
    text, count = max(counts.items(), key=lambda kv: kv[1])
    return text if count >= max(2, 0.3 * len(pages)) else None


def split_head_foot(lines, img_h, head_text):
    """拆出页眉、页码和正文行；返回 (正文行, 页码或 None)。"""
    body, page_no = [], None
    for line in lines:
        if head_text and line["text"] == head_text:
            continue
        if line["top"] >= FOOT_BAND * img_h and PAGE_NUM_RE.match(line["text"]):
            page_no = int(line["text"])
            continue
        body.append(line)
    return sorted(body, key=lambda l: (l["top"], l["left"])), page_no


def page_densities(path, lines):
    """给每行算「单位字格的墨迹量」：这本书的小标题字号和正文一样，只靠加粗区分。"""
    try:
        img = Image.open(path).convert("L")
    except OSError:
        return
    width, height = img.size
    ink = img.point([255 if v < INK_LEVEL else 0 for v in range(256)])
    for line in lines:
        x0, x1 = max(0, int(line["left"])), min(width, int(line["right"]))
        y0, y1 = max(0, int(line["top"])), min(height, int(line["bottom"]))
        if x1 <= x0 or y1 <= y0:
            continue
        dark = sum(1 for v in ink.crop((x0, y0, x1, y1)).tobytes() if v)
        line["density"] = dark / max((y1 - y0) * max(line["chars"], 1), 1)


def assemble_paragraphs(body):
    """按行坐标还原段落：首行缩进、或上一行提前结束、或行距明显变大＝新段落。"""
    if not body:
        return []
    body = sorted(body, key=lambda l: (l["top"], l["left"]))
    widths = [l["char_w"] for l in body if l["chars"] >= 3]
    char_w = statistics.median(widths) if widths else 10.0
    lefts = sorted(l["left"] for l in body)
    body_left = lefts[max(0, int(len(lefts) * 0.1))]
    body_right = max(l["right"] for l in body)
    prose_dens = [l["density"] for l in body if l.get("density") and l["chars"] >= 18]
    median_dens = statistics.median(prose_dens) if prose_dens else 0

    paras = []
    for line in body:
        text = line["text"]
        if not paras:
            paras.append({"lines": [line]})
            continue
        prev = paras[-1]["lines"][-1]
        continues = text[:1] in CONTINUE_PUNCT          # 行首是收尾标点＝上一行的续行
        bullet = bool(BULLET_RE.match(text))            # （1）/(1)/1./① 开头＝新条目
        indented = (line["left"] - body_left) > 1.5 * char_w
        shifted = (line["left"] - body_left) > 0.5 * char_w
        prev_short = (body_right - prev["right"]) > 2.0 * char_w
        long_gap = (line["top"] - prev["bottom"]) > max(2.5 * char_w, 20)
        if not continues and (bullet or indented or (prev_short and shifted) or long_gap):
            paras.append({"lines": [line]})
        else:
            paras[-1]["lines"].append(line)

    for para in paras:
        parts = []
        for line in para["lines"]:
            text = line["text"]
            if parts and parts[-1][-1:].isascii() and parts[-1][-1:].isalnum() \
                    and text[:1].isascii() and text[:1].isalnum():
                parts.append(" ")
            parts.append(text)
        para["text"] = "".join(parts).strip()
        para["bbox"] = (min(l["left"] for l in para["lines"]),
                        min(l["top"] for l in para["lines"]),
                        max(l["right"] for l in para["lines"]),
                        max(l["bottom"] for l in para["lines"]))
        para["char_h"] = statistics.median(l["char_h"] for l in para["lines"])
        para["density"] = statistics.median(l.get("density", 0) for l in para["lines"])
        # 小标题：加粗（单位字格墨迹明显更多）且是短行
        para["heading"] = (bool(median_dens) and para["density"] > 1.3 * median_dens
                           and len(para["text"]) <= 30)
    return [p for p in paras if p["text"]]


# --------------------------------------------------------- 表格/图 区块

def open_ink(path):
    """二值化后的页面图（墨迹=255）与尺寸，供行/列墨迹分布复用。"""
    img = Image.open(path).convert("L")
    lut = [255 if v < INK_LEVEL else 0 for v in range(256)]
    return img.point(lut), img.size[0], img.size[1]


def row_ink_profile(ink, height):
    """每行墨迹占比（0~1）：缩到宽 1 做 BOX 滤波求行均值，避免逐像素慢跑。"""
    return [v / 255.0 for v in ink.resize((1, height), Image.BOX).tobytes()]


def find_blocks(body, path, img_w, img_h):
    """找出「表 x-y」「图 x-y」区块 → [{'caption','lines','box'}]。

    边界取上下最近的「正文行」（含加粗小标题）或另一个表/图标题：
    标题在图上方（表）就向下取到正文为止，标题在下方（图）就向上取到正文为止。
    """
    blocks = []
    try:
        ink, _, _ = open_ink(path)
    except OSError:
        return blocks
    rows = row_ink_profile(ink, img_h)
    height = len(rows)
    dens = [l["density"] for l in body if l.get("density") and l["chars"] >= 18]
    median_dens = statistics.median(dens) if dens else 0
    gap_cache = {}

    def internal_gap(line, gap=24):
        """行内部有没有大片空白。表格单元格（含被合并成一行表头）之间有大空白，
        整行排印正文没有——这是把表头行和正文行区分开的关键。"""
        key = id(line)
        if key in gap_cache:
            return gap_cache[key]
        x0, x1 = max(0, int(line["left"])), min(img_w, int(line["right"]))
        y0, y1 = max(0, int(line["top"])), min(img_h, int(line["bottom"]))
        result = False
        if x1 - x0 > 4 and y1 - y0 > 4:
            cols = list(ink.crop((x0, y0, x1, y1)).resize((x1 - x0, 1), Image.BOX).tobytes())
            idx = [i for i, v in enumerate(cols) if v > 8]
            if idx:
                run = best = 0
                for v in cols[idx[0]:idx[-1] + 1]:
                    run = run + 1 if v <= 8 else 0
                    best = max(best, run)
                result = best >= gap
        gap_cache[key] = result
        return result

    def is_paragraph(line):
        """真正的排印正文行：整行铺满版面、汉字够多，或以句末标点收尾。
        排除表格短单元格、图表纵轴标题「年化收益率」、横轴刻度 "510 15202530"。
        注意不能用「行内有没有大空白」来判定——中文两端对齐的正文行本身就
        带 28~56px 的疏排空隙，和表格单元格的间隔重叠。"""
        if line["text"][-1:] in "。！？…”":
            return True
        cjk = len(re.findall(r"[\u4e00-\u9fff]", line["text"]))
        return cjk >= 8 and (line["right"] - line["left"]) > 0.4 * img_w

    def is_bold(line):
        """加粗＝单位字格墨迹明显偏多。表头单元格也是加粗的，所以还要看是不是
        成行的标题：汉字够多、够宽、行内没有大片空白（"超越"这种表头单元格不算）。"""
        if not median_dens or line.get("density", 0) <= 1.3 * median_dens:
            return False
        cjk = len(re.findall(r"[\u4e00-\u9fff]", line["text"]))
        return (cjk >= 4 and (line["right"] - line["left"]) > 150
                and not internal_gap(line))

    def is_caption(line):
        """图题：以「表/图 x-y」或「续表」开头，且不是正文里的引用句。
        「表3-1所示。」「表10-5为…」这类是行被折行后落在行首的正文，必须排除。"""
        text = line["text"].strip()
        if line["chars"] > 30 or text[-1:] in "。！？，、":
            return False
        match = CAPTION_RE.match(text) or CONT_RE.match(text)
        if not match:
            return False
        tail = text[match.end():].lstrip(" 　:：")
        return not tail.startswith(("所示", "所不", "所述", "如下", "可见", "见", "为", "是"))

    def ink_rows(start, end):
        start, end = max(0, int(start)), min(height, int(end))
        return sum(1 for i in range(start, end) if rows[i] > BLANK_ROW * 3)

    for line in body:
        if not is_caption(line):
            continue
        # 上方只认真正的正文（否则图表内的加粗标注会把边界切进图里）；
        # 下方还把加粗小标题算进去，免得表把后面的小标题吞掉
        above = [l for l in body if (is_paragraph(l) or is_caption(l))
                 and l["bottom"] <= line["top"] - 1]
        below = [l for l in body if (is_paragraph(l) or is_bold(l) or is_caption(l))
                 and l["top"] >= line["bottom"] + 1]
        lo = int(max((l["bottom"] for l in above), default=0) + 6)
        hi = int(min((l["top"] for l in below), default=img_h) - 6)
        cap_top, cap_bottom = int(line["top"]), int(line["bottom"])
        if hi <= lo:
            continue
        if ink_rows(lo, cap_top) >= ink_rows(cap_bottom, hi):
            box_top, box_bottom = lo, min(img_h, cap_bottom + 8)   # 图在标题上方
        else:                                                       # 表在标题下方
            box_top, box_bottom = max(0, cap_top - 8), hi
        if box_bottom - box_top < 40 or (box_bottom - box_top) > 0.85 * img_h:
            box_top, box_bottom = 0, img_h        # 兜底：整页
        inside = [l for l in body if box_top <= l["cy"] <= box_bottom]
        blocks.append({"caption": line["text"], "lines": inside,
                       "box": (0, box_top, img_w, box_bottom)})

    # 兜底：原书图题被 OCR 漏掉、或跨页续表只印了表体的页，
    # 用「一长串非正文行」把这块区域也圈出来，别让它当散字混进正文
    covered = {id(l) for b in blocks for l in b["lines"]}
    runs, current = [], []
    for line in body:
        textlike = (id(line) in covered or is_paragraph(line)
                    or is_bold(line) or is_caption(line))
        if textlike:
            if current:
                runs.append(current)
                current = []
        else:
            current.append(line)
    if current:
        runs.append(current)
    for run in runs:
        span = run[-1]["bottom"] - run[0]["top"]
        if len(run) < 6 or span < 100:
            continue
        # 把紧邻上方的孤立碎屑行（表题与表体被拆开时的残片）也吞进区块
        top0 = run[0]["top"]
        crumbs = [l for l in body if l not in run and 0 < top0 - l["bottom"] < 60
                  and not is_paragraph(l) and not is_caption(l)]
        if crumbs and len(crumbs) <= 5:
            top0 = min(top0, min(l["top"] for l in crumbs))
        box_top, box_bottom = int(max(0, top0 - 6)), int(min(img_h, run[-1]["bottom"] + 6))
        if box_bottom - box_top > 0.85 * img_h:
            box_top, box_bottom = 0, img_h
        blocks.append({"caption": "无题表（原书图题未识别，或为跨页续表）",
                       "lines": run, "box": (0, box_top, img_w, box_bottom)})
    blocks.sort(key=lambda b: b["box"][1])
    return blocks


# ------------------------------------------------------------- Markdown

def crop_image(src, box, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.open(src).crop(box).save(dst, quality=88)
    return dst


def render_page(page, args, assets_dir, head_text):
    """单页 → markdown 行列表。"""
    body, printed = split_head_foot(page["lines"], page["h"], head_text)
    page_densities(page["path"], body)
    blocks = find_blocks(body, page["path"], page["w"], page["h"]) if args.images else []

    chunk = [f"<!-- idx:{page['index']} img:{Path(page['member']).name}"
             + (f" page:{printed}" if printed else "") + " -->"]
    if not blocks:
        chunk += [("### " if p["heading"] else "") + p["text"]
                  for p in assemble_paragraphs(body)]
        return chunk

    rest = list(body)
    for index, block in enumerate(blocks, 1):
        top, bottom = block["box"][1], block["box"][3]
        above = [l for l in rest if l["top"] < top - 1]
        rest = [l for l in rest if l["top"] >= bottom - 1]
        chunk += [("### " if p["heading"] else "") + p["text"]
                  for p in assemble_paragraphs(above)]
        caption = block["caption"] or "插图"
        name = f"{Path(page['member']).stem}_{re.sub(r'[^0-9A-Za-z一-龥]', '', caption)}"
        if not CAPTION_RE.match(caption):
            name += f"_{index}"                # 续表/无题表：一页可能有多个
        name += ".jpg"
        crop_image(page["path"], block["box"], assets_dir / name)
        # md 在 chapters/ 下，图片在输出根目录的 assets/ 下，所以要带 ../
        rel = posixpath.join("..", args.assets_name, name)
        key = f"{Path(page['member']).name}::{caption}"
        entry = args.table_map.get(key)
        if isinstance(entry, str):
            entry = {"markdown": entry}
        args.dump.setdefault(key, {"caption": caption, "asset": rel,
                                   "image": Path(page["member"]).name,
                                   "page": printed or page["index"], "markdown": ""})
        if entry and entry.get("markdown"):
            # 人工/视觉模型转录过的表：结构化文本在前，原图在后留证
            chunk += ["", f"**{caption}**", "", entry["markdown"].rstrip(), ""]
            if entry.get("note"):
                chunk += [f"> 注：{entry['note']}", ""]
            chunk.append(f"[原图]({rel})")
            continue
        chunk.append(f"![{caption}]({rel})")
        if entry and entry.get("note"):
            # 截图类图块（软件界面/Excel 操作图）：只贴图 + 一句说明，不写"未转录"
            chunk.append(f"> 注：{entry['note']}")
            continue
        if not args.keep_garbled:
            chunk.append("> ⚠️ 该表尚未转录为结构化表格，数字请见上方原图。")
            continue
        raw = "\n".join(l["text"] for l in sorted(block["lines"], key=lambda l: l["top"]))
        chunk.append("<details><summary>该区域的 OCR 原始文本（数字不可靠，"
                     "请以上图为准）</summary>\n\n```\n" + raw + "\n```\n\n</details>")
    chunk += [("### " if p["heading"] else "") + p["text"]
              for p in assemble_paragraphs(rest)]
    return chunk


def cn_to_int(text):
    """章号用：中文数字转 int（一到九十九），失败返回 0。"""
    text = text.strip()
    if text.isdigit():
        return int(text)
    if not text or any(c not in CN_DIGITS + "十" for c in text):
        return 0
    if "十" not in text:
        return CN_DIGITS.index(text) if len(text) == 1 else 0
    head, _, tail = text.partition("十")
    return (CN_DIGITS.index(head) if head else 1) * 10 + (CN_DIGITS.index(tail) if tail else 0)


def entry_order(title):
    match = re.match(r"^第([一二三四五六七八九十百零〇0-9]+)章", title)
    return cn_to_int(match.group(1)) if match else 0


def group_entries(entries):
    """把 TOC 条目按章分组：章条目开头，其后的节归入该章。"""
    groups = []
    for entry in entries:
        if CHAPTER_RE.match(entry["title"]) or not groups:
            groups.append([entry])
        else:
            groups[-1].append(entry)
    return groups


def cjk_key(text):
    """只留汉字，用于把「第一章1」这类扫描噪声和目录标题对上。"""
    return re.sub(r"[^\u4e00-\u9fff]", "", text)


def match_entry(text, candidates):
    """行文本匹配到哪个目录条目（取最长命中），匹配不上返回 None。"""
    key = cjk_key(text)
    if len(key) < 2:
        return None
    best = None
    for title_key, entry in candidates.items():
        if len(title_key) >= 2 and (key in title_key or title_key in key):
            if best is None or len(title_key) > len(best[0]):
                best = (title_key, entry)
    return best[1] if best else None


def write_group(group, args, chapters_dir, assets_dir, zf, work_dir, cache_dir,
                foreign_keys=frozenset()):
    """OCR 一章（含其下各节）并写出一个 md。"""
    head = group[0]["title"]
    plan = [(e["title"], member) for e in group for member in e["pages"]]
    if not plan:
        return None

    pages = []
    for index, (title, member) in enumerate(plan, 1):
        local = work_dir / Path(member).name
        if not local.exists():
            local.write_bytes(zf.read(member))
        lines, img_w, img_h = ocr_page_cached(local, member, cache_dir)
        if lines is None:
            print(f"⚠️  OCR 失败: {member}", file=sys.stderr)
            continue
        pages.append({"index": index, "title": title, "member": member, "path": local,
                      "w": img_w, "h": img_h, "lines": to_pixels(lines, img_w, img_h)})

    head_text = running_head_of(pages)
    candidates = {cjk_key(e["title"]): e for e in group if len(cjk_key(e["title"])) >= 2}
    emitted = {cjk_key(head)}

    md = [f"# {head}", ""]
    for page in pages:
        # 扫描页上常常印着本章/本节的标题：以它的实际位置生成标题，并从正文里删掉
        visual = None
        kept = []
        for line in page["lines"]:
            if not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", line["text"]):
                continue                                    # 纯符号的扫描噪声
            entry = match_entry(line["text"], candidates) if line["chars"] <= 40 else None
            if entry is not None:
                visual = visual or entry
                continue
            key = cjk_key(line["text"])
            if line["chars"] <= 30 and any(
                    k in key or (len(key) >= 2 and key in k) for k in foreign_keys):
                continue                                    # 下一章的扉页/书眉
            kept.append(line)
        page["lines"] = kept
        own = candidates.get(cjk_key(page["title"]))
        for entry in (own, visual):        # 先补该页归属的标题，再补页内新出现的标题
            key = cjk_key(entry["title"]) if entry else None
            if entry and key not in emitted:
                emitted.add(key)
                md += [f"## {entry['title']}", ""]
        md += render_page(page, args, assets_dir, head_text)
        md.append("")

    order = entry_order(head)
    safe = re.sub(r"[\\/:*?\"<>|]", "_", head)[:60]
    chapters_dir.mkdir(parents=True, exist_ok=True)
    out_file = chapters_dir / (f"{order:02d}-{safe}.md" if order else f"{safe}.md")
    out_file.write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")
    print(f"✅ {out_file.name}  （{len(pages)} 页，书眉: {head_text!r}）")
    return out_file


# ------------------------------------------------------------------- main

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="把扫描版 EPUB 转成 Markdown（macOS Vision OCR）")
    parser.add_argument("epub", help="EPUB 文件路径")
    parser.add_argument("-o", "--out", help="输出目录（默认：EPUB 同级的 <书名>_md）")
    parser.add_argument("--only", help="只处理标题匹配该正则的章（含其下的节）")
    parser.add_argument("--no-images", action="store_true", help="不裁剪表格/插图")
    parser.add_argument("--assets-name", default="assets", help="图片目录名（默认 assets）")
    parser.add_argument("--tables", help="表格转录 JSON（键为 <图片名>::<表标题>，值为 markdown）")
    parser.add_argument("--dump-tables", help="把本次识别到的全部表/图写成转录 JSON 骨架")
    parser.add_argument("--keep-garbled", action="store_true",
                        help="未转录的表仍保留 OCR 乱码文本（默认丢弃，只留原图提示）")
    parser.add_argument("--list", action="store_true", help="只列出 TOC，不转换")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    args.images = not args.no_images
    args.table_map = {}
    if args.tables:
        table_path = Path(args.tables).expanduser()
        args.table_map = json.loads(table_path.read_text(encoding="utf-8"))
        # 表格正文可以写成独立 .md 文件（相对本 JSON 目录），方便逐张转录
        for entry in args.table_map.values():
            if isinstance(entry, dict) and entry.get("file") and not entry.get("markdown"):
                entry["markdown"] = (table_path.parent / entry["file"]).read_text(
                    encoding="utf-8")
        print(f"📊 载入表格转录 {len(args.table_map)} 条：{table_path.name}")
    args.dump = {}
    epub_path = Path(args.epub).expanduser()
    if not epub_path.exists():
        print(f"❌ 找不到 EPUB: {epub_path}", file=sys.stderr)
        return 1

    zf, docs, toc, title = read_epub(epub_path)
    stream = build_stream(docs)
    pages = assign_pages(stream, toc)
    print(f"📖 {title}")
    print(f"   {len(docs)} 个 XHTML、{len(toc)} 个目录条目、{len(pages)} 页图片")

    if args.list:
        for entry in toc:
            print(f"   {len(entry['pages']):3d} 页  {entry['title']}")
        return 0

    groups = group_entries(toc)
    all_keys = {cjk_key(g[0]["title"]) for g in groups}
    if args.only:
        pattern = re.compile(args.only)
        groups = [g for g in groups if pattern.search(g[0]["title"])]
        if not groups:
            print(f"❌ 没有匹配 {args.only!r} 的章", file=sys.stderr)
            return 1

    out_dir = Path(args.out).expanduser() if args.out \
        else epub_path.parent / f"{epub_path.stem}_md"
    chapters_dir = out_dir / "chapters"
    assets_dir = out_dir / args.assets_name
    cache_dir = out_dir / ".ocr_cache"
    out_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        for group in groups:
            foreign = all_keys - {cjk_key(group[0]["title"])}
            write_group(group, args, chapters_dir, assets_dir, zf, work_dir, cache_dir,
                        foreign_keys=foreign)

    if args.dump_tables:
        dump_path = Path(args.dump_tables).expanduser()
        dump_path.write_text(json.dumps(args.dump, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        print(f"📝 表格骨架已写出：{dump_path}（{len(args.dump)} 条）")

    print(f"📁 输出：{out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
