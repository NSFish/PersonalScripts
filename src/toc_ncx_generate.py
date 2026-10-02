#!/usr/bin/env python3
"""扫描 xhtml 目录生成 EPUB 的 toc.ncx（阅读器导航目录）。

替代原 shell script/toc_ncx_generate.sh：用 lxml 解析与构建 XML，
不再依赖 xmlstarlet，也不再用 mktemp 暂存卷/章片段。

分类规则（与旧版一致，按 <title> 文本判断）：
- `^第X卷/部(空格或结束)` → 分部（开启一个新的 volume 层级）
- `^番外(空格或结束)`     → 分部（与卷/部同级）
- `^第X章(空格或结束)`     → 章（归入当前分部；无分部时直接挂 navMap）
- 其余                    → 当作章处理（打印注意信息）

输出到 xhtml 文件夹的父目录 toc.ncx。
"""
import argparse
import re
import sys
from pathlib import Path

XHTML_NS = "http://www.w3.org/1999/xhtml"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"

# 与旧脚本 grep -P 等价的分类规则
VOLUME_RE = re.compile(r"^第[^ ]+[卷部](\s|$)")
EXTRA_RE = re.compile(r"^番外(\s|$)")
CHAPTER_RE = re.compile(r"^第[^ ]+章(\s|$)")


def extract_title(xhtml: Path) -> str | None:
    """读取 xhtml 的 <head><title>，不存在或为空返回 None。"""
    try:
        from lxml import etree
        tree = etree.parse(str(xhtml))
    except Exception:
        return None
    node = tree.find(f"{{{XHTML_NS}}}head/{{{XHTML_NS}}}title")
    if node is None or not (node.text or "").strip():
        return None
    return node.text


def classify(title: str) -> str:
    """返回 'volume' | 'chapter'。"""
    if VOLUME_RE.search(title) or EXTRA_RE.search(title):
        return "volume"
    return "chapter"


def chapter_width(total: int) -> int:
    """章节 ID 的数字宽度，与旧脚本一致（按总文件数分档）。"""
    for limit, width in ((10, 1), (100, 2), (1000, 3), (10000, 4), (100000, 5)):
        if total < limit:
            return width
    return 6


def xml_escape(text: str) -> str:
    """转义 XML 文本里的 & < >。

    旧 shell 版把 xmlstarlet 取出的（已反转义）标题原样拼回 XML，
    标题含 & < 时会产出非法 XML；这里转义后输出始终合法。
    对不含特殊字符的标题，输出与旧版逐字节一致。
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nav_point(nid: str, play_order: int, title: str, src: str,
              indent: int, children: list[str] | None = None) -> str:
    """生成一个 navPoint 片段（缩进由 indent 控制，与旧脚本一致）。"""
    pad = " " * indent
    head = (f'{pad}<navPoint id="{nid}" playOrder="{play_order}">\n'
            f'{pad}    <navLabel><text>{xml_escape(title)}</text></navLabel>\n'
            f'{pad}    <content src="{xml_escape(src)}"/>')
    if children:
        return head + "\n" + "\n".join(children) + f"\n{pad}</navPoint>"
    return head + f"\n{pad}</navPoint>"


def build_ncx(xhtml_dir: Path) -> tuple[str, dict]:
    """生成 toc.ncx 文本与统计信息。"""
    files = sorted(xhtml_dir.glob("*.xhtml"))
    if not files:
        raise FileNotFoundError(f"在 '{xhtml_dir}' 中未找到任何 xhtml 文件")

    folder_name = xhtml_dir.name
    width = chapter_width(len(files))

    play_order = 0
    volume_count = 0
    volume_part_count = 0
    extra_count = 0
    chapter_count = 0

    navpoints: list[str] = []          # 已完成的顶层 navPoint
    current_volume: dict | None = None  # 当前未关闭的分部及其章节

    for f in files:
        title = extract_title(f)
        if title is None:
            print(f"警告: 无法从文件 '{f.name}' 中提取标题，已跳过")
            continue

        play_order += 1
        src = f"{folder_name}/{f.name}"

        if classify(title) == "volume":
            if VOLUME_RE.search(title):
                volume_part_count += 1
            else:
                extra_count += 1
            # 关闭上一个未完成的卷
            if current_volume is not None:
                navpoints.append(nav_point(
                    current_volume["id"], current_volume["play_order"],
                    current_volume["title"], current_volume["src"], 8,
                    current_volume["chapters"] or None))
                current_volume = None

            volume_count += 1
            current_volume = {
                "id": f"volume_{volume_count:02d}",
                "play_order": play_order,
                "title": title,
                "src": src,
                "chapters": [],
            }
        else:
            if not CHAPTER_RE.search(title):
                print(f"注意: 文件 '{f.name}' 的标题 '{title}' 无法分辨类型，当作章节处理")
            chapter_count += 1
            cid = f"chapter_{chapter_count:0{width}d}"
            child = nav_point(cid, play_order, title, src, 12)
            if current_volume is not None:
                current_volume["chapters"].append(child)
            else:
                navpoints.append(nav_point(cid, play_order, title, src, 8))

    # 关闭最后一个分部
    if current_volume is not None:
        navpoints.append(nav_point(
            current_volume["id"], current_volume["play_order"],
            current_volume["title"], current_volume["src"], 8,
            current_volume["chapters"] or None))

    depth = 2 if volume_count > 0 else 1
    body = "\n".join(navpoints)
    ncx = (
        '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
        '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" '
        '"http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
        f'<ncx xmlns="{NCX_NS}" version="2005-1">\n'
        '    <head>\n'
        '        <meta name="dtb:uid" content=""/>\n'
        f'        <meta name="dtb:depth" content="{depth}"/>\n'
        '        <meta name="dtb:totalPageCount" content="0"/>\n'
        '        <meta name="dtb:maxPageNumber" content="0"/>\n'
        '    </head>\n'
        '    <docTitle>\n'
        '        <text>目录</text>\n'
        '    </docTitle>\n'
        '    <navMap>\n'
        f'{body}\n'
        '    </navMap>\n'
        '</ncx>\n'
    )
    stats = {"volume_count": volume_count, "volume_part_count": volume_part_count,
             "extra_count": extra_count, "chapter_count": chapter_count,
             "width": width}
    return ncx, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="扫描 xhtml 目录生成 EPUB 的 toc.ncx")
    parser.add_argument("xhtml_dir", help="xhtml 文件夹路径")
    args = parser.parse_args()

    xhtml_dir = Path(args.xhtml_dir).expanduser().resolve()
    if not xhtml_dir.is_dir():
        print(f"错误: 文件夹 '{xhtml_dir}' 不存在")
        sys.exit(1)

    try:
        ncx, stats = build_ncx(xhtml_dir)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)

    out = xhtml_dir.parent / "toc.ncx"
    out.write_text(ncx, encoding="utf-8")

    print(f"已在 '{xhtml_dir.parent}' 目录生成 toc.ncx 文件，包含:")
    if stats["volume_count"] > 0:
        vc, vp, ec = (stats["volume_count"], stats["volume_part_count"],
                      stats["extra_count"])
        if vp > 0 and ec > 0:
            print(f" - {vc} 个分部 ({vp} 个卷/部 + {ec} 个番外)")
        elif vp > 0:
            has_volume = any(
                VOLUME_RE.search(extract_title(f) or "")
                for f in sorted(xhtml_dir.glob("*.xhtml")))
            print(f" - {vc} 个{'分卷' if has_volume else '分部'}")
        elif ec > 0:
            print(f" - {vc} 个番外")
        else:
            print(f" - {vc} 个分部")
    print(f" - {stats['chapter_count']} 个章节 (ID宽度: {stats['width']})")


if __name__ == "__main__":
    main()
