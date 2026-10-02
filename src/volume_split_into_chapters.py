#!/usr/bin/env python3
"""按章节信息文件（标题+起始页）把一卷图片拆分成章节子文件夹。

章节信息文件每行一条，支持三种写法：
  "1 第一章 3"    数字编号 + 标题 + 起始页
  "特别篇 128"    纯标题 + 起始页
  "第二章 65"     中文编号标题 + 起始页

图片从"目录页"的下一页开始按顺序分配给各章节，每章落进输出目录下的同名子文件夹。

起始页写的是"章节在目录页之后的第几页"（从 1 计）：
第一章从目录页下一页开始就写 1；同一起始页可出现多次（后续章节页数为 0）。
最后一章吃掉目录页之后剩余的全部页。
输出目录为 `<输入目录名>_split`（与输入同级）。
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

from _common import is_image_file, natural_key


def parse_contents_file(contents_path: Path) -> list[tuple[str, int]]:
    """解析章节信息文件，返回 [(标题, 起始页)]，按起始页升序。"""
    chapters = []
    for line in contents_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        # 数字编号+标题+起始页：把编号并入标题，保证输出目录名带序号
        m = re.match(r"(\d+)\s+([^\d]+?)\s+(\d+)$", line)
        if m:
            chapters.append((f"{m.group(1)} {m.group(2).strip()}", int(m.group(3))))
            continue
        # 纯标题+起始页（标题本身可以是 "第二章" 这类中文编号）
        m = re.match(r"(.+?)\s+(\d+)$", line)
        if m:
            chapters.append((m.group(1).strip(), int(m.group(2))))
    return sorted(chapters, key=lambda x: x[1])


def chapter_page_counts(starts: list[int], available: int) -> list[int]:
    """按相邻章节的起始页差算各章页数，最后一章吃余下所有页。"""
    counts = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
    counts.append(available - sum(counts))
    return counts


def organize_manga(input_dir: Path, dir_page: str, contents_path: Path, output_dir: Path) -> int:
    """把 input_dir 拆成章节子文件夹放进 output_dir；返回失败章节数。"""
    chapters = parse_contents_file(contents_path)
    if not chapters:
        print(f"错误: 未在 {contents_path.name} 中找到有效的章节信息")
        return 1

    pages = sorted((p.name for p in input_dir.iterdir() if p.is_file() and is_image_file(p)), key=natural_key)
    if dir_page not in pages:
        print(f"错误: 目录页 {dir_page} 未在文件夹中找到")
        return 1

    available = len(pages) - pages.index(dir_page) - 1  # 目录页之后的正文页数
    counts = chapter_page_counts([start for _, start in chapters], available)

    output_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    pages = pages[pages.index(dir_page) + 1:]  # 从目录页下一页开始分配
    for (title, _), count in zip(chapters, counts):
        if count < 0:
            # 起始页跨度超过实际页数时 range() 会静默空转，这里明确报出来
            print(f"⚠️ 章节 [{title}] 算出的页数是 {count}（起始页超出实际页数），跳过")
            failures += 1
            continue

        chapter_dir = output_dir / title
        chapter_dir.mkdir(exist_ok=True)
        saved = 0
        for page in pages[:count]:
            shutil.copy2(input_dir / page, chapter_dir / page)
            saved += 1
        pages = pages[count:]
        print(f"章节 [{title}] 已保存 {saved} 页")

    print(f"\n处理完成! 共拆分 {len(chapters)} 个章节到目录: {output_dir}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="按章节信息文件把一卷图片拆分成章节子文件夹")
    parser.add_argument("input_dir", help="漫画图片文件夹路径")
    parser.add_argument("dir_page", help='目录页文件名 (如 "6.jpg")')
    parser.add_argument("contents_file", help="章节信息文件路径")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    if not input_dir.is_dir():
        print(f"错误: 目录 '{input_dir}' 不存在")
        return 1
    contents_path = Path(args.contents_file).resolve()
    if not contents_path.is_file():
        print(f"错误: 章节信息文件 '{contents_path}' 不存在")
        return 1

    output_dir = input_dir.parent / f"{input_dir.name}_split"
    try:
        return 1 if organize_manga(input_dir, args.dir_page, contents_path, output_dir) else 0
    except Exception as e:
        print(f"错误: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
