#!/usr/bin/env python3
"""扫描文件夹，统计图片主流宽度并按文件名排序列出不符合的图片。

替代原 check_page_width.sh：用 Pillow 读取宽度（跨平台，不再依赖 macOS 的 sips）。
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

from _common import is_image_file, IMAGE_EXTS


def main() -> None:
    parser = argparse.ArgumentParser(
        description="统计指定文件夹中图片的主流宽度，并按文件名排序列出不符合的图片"
    )
    parser.add_argument("target_dir", help="图片文件夹路径")
    args = parser.parse_args()

    target = Path(args.target_dir).resolve()
    if not target.is_dir():
        print(f"错误：文件夹 '{args.target_dir}' 不存在或无法访问！")
        sys.exit(1)

    print(f"正在扫描文件夹：{target}")
    print(f"支持的图片格式：{' '.join(IMAGE_EXTS)}")
    print("----------------------------------------")

    records = []  # (width, filename)
    for f in target.iterdir():
        if not f.is_file():
            continue
        if not is_image_file(f):
            continue
        try:
            with Image.open(f) as img:
                width = img.width
        except Exception:
            continue
        if width and width > 0:
            records.append((width, f.name))

    if not records:
        print("错误：文件夹中未找到支持的图片文件！")
        sys.exit(1)

    widths = [w for w, _ in records]
    main_width, main_count = Counter(widths).most_common(1)[0]
    total = len(records)

    unmatched = sorted(name for w, name in records if w != main_width)
    unmatched_str = "、".join(unmatched)

    print(f"扫描完成！共检测到 {total} 张图片")
    print("----------------------------------------")
    print(f"主流图片宽度：{main_width} 像素（共 {main_count} 张）")

    if unmatched_str:
        print(f"不符合的图片（按文件名排序）：{unmatched_str}")
    else:
        print(f"所有图片宽度均为 {main_width} 像素")


if __name__ == "__main__":
    main()
