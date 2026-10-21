#!/usr/bin/env python3
"""本子漫画质量体检：分辨率 / 等效 dpi / 体积密度 / 细节 / 混叠 / 尺寸一致性 → 分级。

用法: python hentai_quality_report.py <输入路径> [选项]

输入路径可以是：
- 单个压缩包（.zip/.cbz）                        → 报告 1 本
- 单张图片                                      → 报告 1 本（1 页）
- 图片文件夹（含子文件夹，递归收集）              → 报告 1 本
- 装着一堆压缩包的文件夹                          → 每包 1 本
- 装着一堆子文件夹的文件夹（每个子文件夹是一本）    → 每子文件夹 1 本

自动识别（--layout auto，默认）按以下顺序判定：
1. 顶层有压缩包 → 每个包一本；
2. 顶层子文件夹内（递归）有图片 → 每个子文件夹一本；
3. 以上都没命中 → 整个文件夹当作一本（递归收集）。
顶层散图：只有前两步都没产出本子时才单独成一本，否则额外作为「<文件夹名>（散图）」报一本。

判定说明（都是启发式，数字会一并打印，请自行复核）：
- 等效 dpi：按 B5（182×257mm）折算，长边像素 ÷ (长边mm/25.4)；横版（w > h×1.2）
  视为見開き，长边按 364mm 算。可用 --long-mm 手动指定物理长边（A4 长边 297）。
- KB/MP：总体积 ÷ 总百万像素，衡量「像素是不是有内容撑着」。重度重压缩或 AI 放大的
  空像素会显著偏低。AVIF/WEBP 等重编码格式本身体积小，该项自动跳过判定。
- 细节（参考指标，不影响分级）：在【固定物理尺寸】区域（默认 2×2 inch，故跨 dpi 可比）
  上做 2× 降采样再升回，残差 ÷ 区域标准差。真实页面 ≈0.02~0.6，放大插值图会再低一个
  量级。⚠️ 但它高度依赖画风：满页细网点的扫图和线稿稀疏的数字原生可以差 10 倍，
  没有同源对照就无法单凭它判定「AI 放大」。用法：同源多版本对比、或处理前后对比。
- 混叠：同区域 LANCZOS 与 NEAREST 两种 2× 降采样之差 ÷ 区域标准差。高值 = 高频能量多
  （低 dpi 图的正常表现，参考值而非硬判据）。

输出：终端表格；--json / --csv 可导出。
"""
import argparse
import csv
import json
import sys
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageFile, ImageStat

from _common import (
    fix_zip_filename,
    is_archive_file,
    is_hidden_part,
    is_image_file,
    iter_files,
    list_archives,
    list_images,
    natural_key,
)

# 单张超大扫描会触发 PIL 的解压炸弹保护，这里是本地可信文件，直接放开
Image.MAX_IMAGE_PIXELS = None
# 个别扫包的尾部数据不完整，尽量读出来而不是整页判失败
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ---------------------------------------------------------------- 判定阈值 ----
# 改这些常量即可调松紧；改完建议跑 tests/test_hentai_quality_report.py 看标定用例。
T_DPI_A = 290.0        # A 档等效 dpi 下限（≈ B5 长边 2900px）
T_DPI_B = 200.0
T_DPI_C = 150.0
T_ALIAS_OK = 0.55      # 混叠（归一化）良好上限
T_ALIAS_BAD = 0.90
T_CONSIST_A = 0.90     # 主尺寸占比：A 档要求
T_CONSIST_B = 0.80

# 体积密度 KB/MP：黑白与彩色分开定阈值。
# 同一内容存彩色比灰度约贵 1.3 倍（实测 JPEG 1.28~1.32 / PNG 1.57~1.76），
# 且密度随 dpi 升高而下降（高 dpi 图平缓区域多，单像素“不值那么多字节”）。
# 实测参照（拟真页面 JPEG q90）：灰度 300dpi≈36 / 600dpi≈26；
# 彩色 300dpi≈46 / 600dpi≈32。真实黑白本子 WEBP ≈108（该格式跳过判定）。
# ⚠️ 密度鉴别力弱：正常 q90 与 4× 放大只差 ~14%，与 q50 强压差 ~36%，
# 且不同画风（满页网点 vs 稀疏线稿）能差 3~7 倍。故只作【参考提示】，不参与判级。
T_KBMP_GRAY = 22.0     # 灰度：低于此提示密度偏低
T_KBMP_COLOR = 28.0    # 彩色：低于此提示密度偏低（约 ×1.3）

# 细节指标仅作参考（画风依赖太强，无法单凭数值判定放大），不设判级阈值。
# 判级只依赖：等效 dpi / 尺寸一致性。
# 细节/密度的实际用法是【同源对比】：同一作品的多个版本互相比较，
# detail 低一个量级、或密度低一截的那个就是被放大/重压缩过的。

# 物理开本（mm）
B5_LONG_MM = 257.0
B5_SPREAD_LONG_MM = 364.0  # 見開き：B5 双页 364×257
ANALYSIS_INCH = 2.0        # 细节分析取的固定物理边长（跨 dpi 可比）


GRAY_MODES = {"1", "L", "LA", "I", "I;16", "I;16B", "I;16L", "I;16N"}
# 这些格式本身就是有损重编码产物，体积密度指标不适用
RECOMPRESSED_FORMATS = {"AVIF", "WEBP"}

GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


# ---------------------------------------------------------------- 数据结构 ----
@dataclass
class Item:
    """本子内的一页：显示名 + 字节数 + 打开方式所需的定位信息。"""
    name: str
    size: int
    path: Path | None = None      # 来自文件夹/单图
    zip_path: Path | None = None  # 来自压缩包
    zip_name: str | None = None   # 包内条目名（原始，未修正）


@dataclass
class Book:
    name: str
    kind: str                     # archive | dir | image
    path: Path
    items: list[Item] = field(default_factory=list)


@dataclass
class Report:
    """单本的质量报告（可直接 JSON 序列化）。"""
    name: str
    kind: str
    source: str
    pages: int
    main_size: str
    main_width: int
    main_height: int
    long_edge: int
    est_dpi: float
    consistent: float
    size_variants: int
    avg_mb: float
    kb_per_mp: float
    color: str
    formats: str
    detail: float
    alias: float
    grade: str
    notes: list[str]
    pages_read: int
    detail_pages: int
    flat_pages: int
    merged_size: str
    off_size_pages: list[str]


# ---------------------------------------------------------------- 收集 --------
def items_from_archive(zp: Path) -> list[Item]:
    """读取压缩包内的图片条目（只查中央目录，不解压）。"""
    out: list[Item] = []
    with zipfile.ZipFile(zp) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            fixed = fix_zip_filename(info)
            if not fixed or not is_image_file(fixed):
                continue
            if any(is_hidden_part(part) for part in fixed.replace("\\", "/").split("/")):
                continue
            out.append(Item(name=fixed, size=info.file_size,
                            zip_path=zp, zip_name=info.filename))
    out.sort(key=lambda it: natural_key(it.name))
    return out


def items_from_dir(dp: Path) -> list[Item]:
    """递归收集文件夹内的图片（排除隐藏文件）。"""
    out = [
        Item(name=str(p.relative_to(dp)), size=p.stat().st_size, path=p)
        for p in iter_files(dp)
        if is_image_file(p)
    ]
    out.sort(key=lambda it: natural_key(it.name))
    return out


def dir_has_images(dp: Path) -> bool:
    """文件夹内（递归）是否存在图片，用于判断子文件夹是不是一本。"""
    return any(is_image_file(p) for p in iter_files(dp))


def build_books(src: Path, layout: str) -> list[Book]:
    """按 layout 规则把输入路径展开成本子列表。"""
    if src.is_file():
        if is_archive_file(src):
            return [Book(name=src.stem, kind="archive", path=src)]
        if is_image_file(src):
            return [Book(name=src.stem, kind="image", path=src)]
        raise SystemExit(f"❌ 不支持的文件类型: {src}（仅支持图片与 .zip/.cbz）")

    books: list[Book] = []

    if layout in ("auto", "archives"):
        for zp in list_archives(src):
            books.append(Book(name=zp.stem, kind="archive", path=zp))
        if layout == "archives":
            return books

    if layout in ("auto", "books"):
        for sub in sorted((p for p in src.iterdir() if p.is_dir()),
                          key=lambda p: natural_key(p.name)):
            if is_hidden_part(sub.name):
                continue
            if dir_has_images(sub):
                books.append(Book(name=sub.name, kind="dir", path=sub))
        if layout == "books":
            return books

    if layout == "book":
        return [Book(name=src.name, kind="dir", path=src)]

    # auto：上面两条都没命中 → 整个文件夹当一本
    if not books:
        return [Book(name=src.name, kind="dir", path=src)]

    # 顶层散图：已有本子时额外报一本，避免漏掉
    if list_images(src):
        books.append(Book(name=f"{src.name}（散图）", kind="dir", path=src))
    return books


# ---------------------------------------------------------------- 读图 --------
def open_item(it: Item) -> Image.Image:
    """打开一页（目录走 Path，压缩包走 ZipFile.open）。"""
    if it.zip_path is not None:
        with zipfile.ZipFile(it.zip_path) as zf:
            with zf.open(it.zip_name) as fp:
                import io

                return Image.open(io.BytesIO(fp.read()))
    return Image.open(it.path)


def sample_indices(total: int, k: int) -> list[int]:
    """从 total 页里均匀抽 k 个下标（含首尾）。k<=0 或 total<=k 时全取。"""
    if k <= 0 or total <= k:
        return list(range(total))
    if k == 1:
        return [total // 2]
    return sorted({round(i * (total - 1) / (k - 1)) for i in range(k)})


def median(values: list[float]) -> float:
    """中位数；空列表返回 0.0。"""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def is_grayish(img: Image.Image) -> bool:
    """模式即灰度直接算；否则抽样比对 RGB 通道差。"""
    if img.mode in GRAY_MODES:
        return True
    small = img.convert("RGB").resize((64, 64), Image.NEAREST)
    r, g, b = small.split()
    d1 = ImageStat.Stat(ImageChops.difference(r, g)).mean[0]
    d2 = ImageStat.Stat(ImageChops.difference(g, b)).mean[0]
    return max(d1, d2) <= 3.0


def best_region(gray: Image.Image, side: int) -> Image.Image:
    """取 side×side 的候选区域中标准差最大的一块（避开纯白页边/装订侧暗角）。

    缩放后再测 stddev：扫图常有整页细网点，逐像素 stddev 会被单像素噪声主导，
    降一遍采样更能代表「这块有没有画」。
    """
    w, h = gray.size
    side = max(min(side, w, h), 8)
    best, best_sd = None, -1.0
    for fx in (0.0, 0.5, 1.0):
        for fy in (0.0, 0.5, 1.0):
            left, top = int((w - side) * fx), int((h - side) * fy)
            region = gray.crop((left, top, left + side, top + side))
            sd = ImageStat.Stat(region.resize((128, 128), Image.NEAREST)).stddev[0]
            if sd > best_sd:
                best_sd, best = sd, region
    return best


def detail_metrics(img: Image.Image, dpi: float,
                   inch: float = ANALYSIS_INCH) -> tuple[float, float]:
    """返回 (细节, 混叠)，均已除以区域标准差归一化。

    取样区域按【物理尺寸】固定（默认 2×2 inch）而非固定像素，这样不同 dpi 的图
    覆盖的是同一块画面，指标才跨 dpi 可比。

    细节：区域 2× 降采样再升回后的平均差 ÷ 区域 stddev
    混叠：同区域 LANCZOS 与 NEAREST 两种 2× 降采样之差 ÷ 区域 stddev
    """
    gray = img.convert("L")
    region = best_region(gray, int(round(inch * dpi)))
    half = (max(region.width // 2, 1), max(region.height // 2, 1))
    lanc = region.resize(half, Image.Resampling.LANCZOS)
    near = region.resize(half, Image.Resampling.NEAREST)
    back = lanc.resize(region.size, Image.Resampling.LANCZOS)
    stddev = ImageStat.Stat(region).stddev[0]
    if stddev < 1.0:
        return 0.0, 0.0  # 近纯色区域（扉页/纯黑页），指标无意义
    detail = ImageStat.Stat(ImageChops.difference(region, back)).mean[0] / stddev
    alias = ImageStat.Stat(ImageChops.difference(lanc, near)).mean[0] / stddev
    return round(detail, 3), round(alias, 3)


def est_dpi(width: int, height: int, long_mm: float | None) -> float:
    """按物理长边折算等效 dpi；long_mm 为 None 时按 B5 / 見開き 自动选。"""
    if long_mm is None:
        long_mm = B5_SPREAD_LONG_MM if width > height * 1.2 else B5_LONG_MM
    return max(width, height) / (long_mm / 25.4)


# ---------------------------------------------------------------- 判定 --------
def judge(consist: float, dpi: float, kbmp: float, is_color: bool,
          alias: float, fmt_main: str) -> tuple[str, list[str]]:
    """按各项指标打分，返回 (等级, 备注列表)。

    判级只依赖可靠指标：等效 dpi / 尺寸一致性。
    密度与细节画风依赖太强、鉴别力弱，只作提示与同源对比的参考值。
    """
    notes: list[str] = []
    if dpi < T_DPI_C:
        notes.append(f"低分辨率({dpi:.0f}dpi)")
    elif dpi < T_DPI_B:
        notes.append(f"分辨率偏低({dpi:.0f}dpi)")
    elif dpi < T_DPI_A:
        notes.append(f"分辨率一般({dpi:.0f}dpi)")

    # 体积密度：黑白/彩色用不同阈值（彩色约贵 1.3 倍）。
    # 重编码格式（AVIF/WEBP）本身体积小，跳过判定。仅作提示，不参与判级。
    recompressed = fmt_main.upper() in RECOMPRESSED_FORMATS
    if recompressed:
        notes.append(f"{fmt_main} 重编码（体积指标不适用）")
    else:
        floor = T_KBMP_COLOR if is_color else T_KBMP_GRAY
        if kbmp < floor:
            tag = "彩" if is_color else "灰"
            notes.append(f"密度偏低({kbmp:.0f}KB/MP，{tag}页参考值≥{floor:.0f})")

    if alias > T_ALIAS_BAD:
        notes.append(f"高频能量高({alias:.2f})")
    elif alias > T_ALIAS_OK:
        notes.append(f"轻微混叠({alias:.2f})")

    if consist < T_CONSIST_B:
        notes.append(f"尺寸混杂({consist:.0%})")
    elif consist < T_CONSIST_A:
        notes.append(f"少量异尺寸({consist:.0%})")

    if dpi >= T_DPI_A and consist >= T_CONSIST_A:
        return "A", notes
    if dpi >= T_DPI_B and consist >= T_CONSIST_B:
        return "B", notes
    if dpi >= T_DPI_C:
        return "C", notes
    return "D", notes


# ---------------------------------------------------------------- 分析 --------
def analyze(book: Book, sample: int, detail_pages: int, long_mm: float | None,
            inch: float) -> Report | None:
    """对一本做体检；无图片返回 None。"""
    if book.kind == "archive":
        items = items_from_archive(book.path)
    elif book.kind == "image":
        items = [Item(name=book.path.name, size=book.path.stat().st_size,
                      path=book.path)]
    else:
        items = items_from_dir(book.path)

    if not items:
        return None

    idxs = sample_indices(len(items), sample)
    detail_idxs = sorted(idxs[:detail_pages])

    sizes: list[tuple[int, int]] = []
    fmts: list[str] = []
    gray_flags: list[bool] = []
    read_errors: list[str] = []

    # 第一遍：【全本】读每页头信息 + 判色彩。
    # 尺寸必须全查——抽样会漏掉「上篇+下篇拼在一起」这类整段异尺寸混入，
    # 也可能因抽样撞上几张异尺寸页而误报「尺寸混杂」。
    # 成本可控：只解析页头不解码像素；is_grayish 对 L/LA/I 等灰度模式直接短路，
    # 只有 RGB 页才需要真正解码（见 is_grayish）。
    for it in items:
        try:
            with open_item(it) as img:
                w, h = img.size
                sizes.append((w, h))
                fmts.append(img.format or "?")
                gray_flags.append(is_grayish(img))
        except Exception as e:
            read_errors.append(f"{it.name}(读取失败: {e})")
            continue

    if not sizes:
        return None

    counter = Counter(sizes)
    (mw, mh), main_count = counter.most_common(1)[0]
    consist = main_count / len(sizes)
    total_bytes = sum(it.size for it in items)
    dpi = est_dpi(mw, mh, long_mm)

    # 第二遍：只对细节页做重采样分析（需要 dpi 来定物理取样区），且只测主尺寸页——
    # 异尺寸页（彩页/扉页）的物理采样率不同，混进来会污染 detail
    details: list[float] = []
    aliases: list[float] = []
    flat_pages = 0  # 无纹理页（平涂扉页/纯白页）计数
    for pos in detail_idxs:
        it = items[pos]
        try:
            with open_item(it) as img:
                if img.size != (mw, mh):
                    continue
                d, a = detail_metrics(img, dpi, inch)
                if d <= 0.0:
                    # 近纯色区域：detail 天然为 0（不是放大），单独计数不参与判定
                    flat_pages += 1
                    continue
                details.append(d)
                aliases.append(a)
        except Exception as e:
            read_errors.append(f"{it.name}(细节分析失败: {e})")

    # 均页体积：全本总字节 ÷ 全本页数
    avg_mb = (total_bytes / len(items)) / (1024 * 1024)

    # 密度（KB/MP）：用全本总体积 ÷ 全本总像素。
    # 逐页算需要解码全部页（慢），这里用主尺寸 × 页数估算总像素，足够作参考。
    main_mp = mw * mh / 1_000_000
    total_mp = main_mp * len(items)
    kbmp = (total_bytes / 1024) / total_mp if total_mp else 0.0

    fmt_main = Counter(fmts).most_common(1)[0][0] if fmts else "?"
    n_gray = sum(1 for g in gray_flags if g)
    n_color = len(gray_flags) - n_gray
    if not gray_flags:
        color, is_color = "?", False
    elif n_color == 0:
        color, is_color = "黑白", False
    elif n_gray == 0:
        color, is_color = "全彩", True
    else:
        # 混合：主体占比高的决定密度阈值，并报出【全本】页数比例
        is_color = n_color > n_gray
        color = f"黑白{n_gray}+彩{n_color}"

    # 细节用【中值】而非均值：本子里常有平涂扉页/纯白页（detail 天然≈0），
    # 均值会被个别平涂页拖低；取中值代表「典型内容页」的细节量。
    detail = median(details)
    alias = median(aliases)

    off_pages = read_errors[:5]
    if len(counter) > 1:
        for (w, h), _n in counter.most_common()[1:]:
            off_pages.append(f"{w}×{h}")
        off_pages = off_pages[:5]

    grade, notes = judge(consist, dpi, kbmp, is_color, alias, fmt_main)

    # 「上篇+下篇拼在一起」检测：异尺寸不是零散几张，而是出现第二簇有规模的尺寸。
    # 判据：除主尺寸外另有某尺寸占全本 ≥20%（单张彩页/表纸/广告页不会到这个比例）。
    total = len(sizes)
    second = counter.most_common()[1] if len(counter) > 1 else None
    merged_size = ""
    if second and total and second[1] / total >= 0.20:
        merged_size = f"{second[0][0]}×{second[0][1]}"
        notes.append(f"疑似多本合并：另有 {merged_size} 共 {second[1]} 页"
                     f"（占 {second[1] / total:.0%}）")

    return Report(
        name=book.name,
        kind=book.kind,
        source=str(book.path),
        pages=len(items),
        main_size=f"{mw}×{mh}",
        main_width=mw,
        main_height=mh,
        long_edge=max(mw, mh),
        est_dpi=round(dpi),
        consistent=round(consist, 3),
        size_variants=len(counter),
        avg_mb=round(avg_mb, 2),
        kb_per_mp=round(kbmp, 1),
        color=color,
        formats=fmt_main,
        detail=round(detail, 3),
        alias=round(alias, 3),
        grade=grade,
        notes=notes,
        pages_read=len(sizes),
        detail_pages=len(details),
        flat_pages=flat_pages,
        merged_size=merged_size,
        off_size_pages=off_pages,
    )


# ---------------------------------------------------------------- 输出 --------
def disp_len(s: str) -> int:
    """显示宽度：CJK 全角字符算 2 列。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def fit(s: str, width: int, left: bool = True) -> str:
    """按显示宽度截断（超出加 …）并补齐到 width。"""
    if disp_len(s) <= width:
        pad = " " * (width - disp_len(s))
        return s + pad if left else pad + s
    out = ""
    cur = 0
    for c in s:
        w = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        if cur + w > width - 1:
            break
        out += c
        cur += w
    out += "…"
    return out + " " * (width - disp_len(out))


def print_table(reports: list[Report]) -> None:
    """终端表格输出。"""
    name_w = min(max((disp_len(r.name) for r in reports), default=20) + 2, 40)
    head = (f"{'判定':<4} {fit('本子', name_w)} {'页数':>5} {'主尺寸':>12} "
            f"{'等效':>7} {'均页':>7} {'KB/MP':>7} {'色彩':>12} {'细节':>6} {'混叠':>5}  备注")
    print(head)
    print("─" * disp_len(head))
    for r in reports:
        row = (f"{r.grade:<4} {fit(r.name, name_w)} {r.pages:>5} {fit(r.main_size, 12, False)} "
               f"{f'{r.est_dpi}dpi':>7} {f'{r.avg_mb}MB':>7} {r.kb_per_mp:>7.0f} "
               f"{fit(r.color, 12)} {r.detail:>6.2f} {r.alias:>5.2f}  {'、'.join(r.notes)}")
        print(row.rstrip())


def print_detail(reports: list[Report]) -> None:
    """--verbose：逐本打印全部指标与异常页。"""
    for r in reports:
        print(f"\n===== [{r.grade}] {r.name} =====")
        print(f"  来源      : {r.source}（{r.kind}）")
        print(f"  页数      : {r.pages}（全查尺寸/色彩，读成功 {r.pages_read} 页，"
              f"其中 {r.detail_pages} 页做细节分析）")
        print(f"  主尺寸    : {r.main_size}（占 {r.consistent:.0%}，共 {r.size_variants} 种尺寸）")
        print(f"  等效 dpi  : {r.est_dpi}（按 B5 长边折算）")
        print(f"  均页体积  : {r.avg_mb} MB   密度: {r.kb_per_mp} KB/MP")
        print(f"  色彩/格式 : {r.color} / {r.formats}")
        print(f"  细节      : {r.detail:.3f}（参考值，画风依赖强；"
              f"同源多版本对比时，低一个量级 = 被放大/重压缩）")
        print(f"  混叠      : {r.alias:.3f}（>{T_ALIAS_OK} 轻微，>{T_ALIAS_BAD} 明显）")
        if r.notes:
            print(f"  备注      : {'、'.join(r.notes)}")
        if r.off_size_pages:
            print(f"  异常页    : {'、'.join(r.off_size_pages)}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="本子漫画质量体检：分辨率/等效dpi/体积密度/细节/混叠/尺寸一致性 → 分级"
    )
    parser.add_argument("input_path", help="输入路径（压缩包/图片/图片文件夹/包文件夹/本子文件夹）")
    parser.add_argument("--layout", default="auto",
                        choices=("auto", "book", "archives", "books"),
                        help="输入结构：auto 自动识别（默认）/book 整夹一本 /archives 每包一本 /books 每子夹一本")
    parser.add_argument("--sample", type=int, default=8,
                        help="每本抽样页数（均匀取，含首尾；0 表示全查，默认 8）")
    parser.add_argument("--detail-pages", type=int, default=3,
                        help="每本做细节/混叠分析的页数（默认 3，调大更准但更慢）")
    parser.add_argument("--long-mm", type=float, default=None,
                        help="物理长边 mm，覆盖自动的 B5(257)/見開き(364) 判断；A4 填 297")
    parser.add_argument("--inch", type=float, default=ANALYSIS_INCH,
                        help=f"细节分析的取样物理边长（默认 {ANALYSIS_INCH} inch）")
    parser.add_argument("--sort", default="grade", choices=("grade", "name", "dpi", "input"),
                        help="排序方式（默认 grade：A 在前）")
    parser.add_argument("--min-grade", default=None, choices=("A", "B", "C", "D"),
                        help="只显示不低于该等级的本子")
    parser.add_argument("--json", dest="json_path", help="导出 JSON 到指定路径")
    parser.add_argument("--csv", dest="csv_path", help="导出 CSV 到指定路径")
    parser.add_argument("--verbose", action="store_true", help="逐本打印完整指标")
    args = parser.parse_args(argv)

    src = Path(args.input_path)
    if not src.exists():
        print(f"❌ 输入路径不存在: {src}")
        return 1

    books = build_books(src, args.layout)
    if not books:
        print(f"❌ {src} 内未找到任何支持的图片或压缩包")
        return 1

    print(f"🔍 输入: {src}")
    print(f"📚 识别到 {len(books)} 本（layout={args.layout}），"
          f"每本抽样 {args.sample or '全部'} 页，其中 {args.detail_pages} 页做细节分析")

    reports: list[Report] = []
    for i, book in enumerate(books, 1):
        try:
            rep = analyze(book, args.sample, args.detail_pages, args.long_mm, args.inch)
        except zipfile.BadZipFile as e:
            print(f"⚠️ [{i}/{len(books)}] {book.name}: 压缩包损坏 ({e})")
            continue
        except Exception as e:
            print(f"⚠️ [{i}/{len(books)}] {book.name}: 分析失败 ({e})")
            continue
        if rep is None:
            print(f"⚠️ [{i}/{len(books)}] {book.name}: 未找到图片")
            continue
        reports.append(rep)
        print(f"   [{i}/{len(books)}] {rep.grade} · {rep.name} "
              f"（{rep.pages} 页 · {rep.main_size} · {rep.est_dpi}dpi）")

    if not reports:
        print("\n❌ 没有可报告的本子")
        return 1

    if args.sort == "grade":
        reports.sort(key=lambda r: (GRADE_ORDER[r.grade], r.name))
    elif args.sort == "name":
        reports.sort(key=lambda r: natural_key(r.name))
    elif args.sort == "dpi":
        reports.sort(key=lambda r: -r.est_dpi)
    # input：保持识别顺序

    if args.min_grade:
        limit = GRADE_ORDER[args.min_grade]
        reports = [r for r in reports if GRADE_ORDER[r.grade] <= limit]

    total_pages = sum(r.pages for r in reports)
    print("\n" + "=" * 100)
    print(f"📊 质量报告 · 共 {len(reports)} 本 / {total_pages} 页")
    print("=" * 100)
    print_table(reports)


    tally = Counter(r.grade for r in reports)
    print("─" * 100)
    print("分级汇总: " + "  ".join(
        f"{g} {tally.get(g, 0)} 本" for g in ("A", "B", "C", "D") if tally.get(g)
    ))
    print(f"A ≈ 300dpi 起 + 尺寸一致≥{T_CONSIST_A:.0%}；B ≈ 200dpi 起；"
          f"C ≈ 150dpi 起；D = 低于此")
    print(f"密度/细节为参考指标（不参与分级）：密度阈值按黑白(≥{T_KBMP_GRAY:.0f})"
          f"/彩色(≥{T_KBMP_COLOR:.0f}) 分开；两者都画风依赖强，"
          f"正确用法是同源多版本对比")

    if args.verbose:
        print_detail(reports)

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps([r.__dict__ for r in reports], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"💾 JSON 已导出: {args.json_path}")
    if args.csv_path:
        with open(args.csv_path, "w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(reports[0].__dict__.keys()))
            writer.writeheader()
            for r in reports:
                row = dict(r.__dict__)
                row["notes"] = "、".join(r.notes)
                row["off_size_pages"] = "、".join(r.off_size_pages)
                writer.writerow(row)
        print(f"💾 CSV 已导出: {args.csv_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
