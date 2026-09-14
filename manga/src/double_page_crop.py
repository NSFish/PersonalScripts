#!/usr/bin/env python3
"""把宽幅双页漫画图按中线裁切成左右两张单页。

输出目录为 `<输入目录名>_split`（与输入同级）。
右页命名为 `<原名>_01`、左页为 `<原名>_02`（日漫右开本顺序）；
非双页图片原样复制过去，保持原文件名。
"""
import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image

from _common import list_images

RATIO_THRESHOLD = 1.4  # 宽/高 超过该比例才视为双页，避免误切单张宽图/封面
SPLIT_SUFFIXES = ("_01", "_02")  # 已拆分产生的子页，避免重复拆分


def is_double_page(image_path: Path) -> bool:
    """判断图片是否为双页：宽高比明显大于 1 才判定为双页。"""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            if not height:
                return False
            return width / height >= RATIO_THRESHOLD
    except Exception as e:
        print(f"分析图片 {image_path.name} 时出错: {e}")
        return False


def split_double_page(image_path: Path, output_dir: Path) -> bool:
    """按中线拆成左右两张；右页 `<名>_01`、左页 `<名>_02`，成功返回 True。"""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            split_pos = width // 2
            right_page = img.crop((split_pos, 0, width, height))
            left_page = img.crop((0, 0, split_pos, height))

            right_path = output_dir / f"{image_path.stem}_01{image_path.suffix}"
            left_path = output_dir / f"{image_path.stem}_02{image_path.suffix}"
            right_page.save(right_path)
            left_page.save(left_path)
    except Exception as e:
        print(f"拆分图片 {image_path.name} 时出错: {e}")
        return False

    print(f"已拆分: {image_path.name} -> {right_path.name} (右) 和 {left_path.name} (左)")
    return True


def process_directory(input_dir: Path, output_dir: Path) -> None:
    """把 input_dir 里的图片拆/复制到 output_dir。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    for src in list_images(input_dir):
        if src.stem.endswith(SPLIT_SUFFIXES):
            continue  # 跳过已拆分的子页，保证幂等
        if is_double_page(src):
            right_path = output_dir / f"{src.stem}_01{src.suffix}"
            left_path = output_dir / f"{src.stem}_02{src.suffix}"
            if right_path.exists() or left_path.exists():
                print(f"⚠️ 跳过(已存在): {src.name}")
                continue
            split_double_page(src, output_dir)
            continue
        dest = output_dir / src.name
        if dest.exists():
            print(f"⚠️ 跳过(已存在): {src.name}")
            continue
        try:
            shutil.copy2(src, dest)
            print(f"复制单页图片: {src.name}")
        except Exception as e:
            print(f"复制单页图片 {src.name} 时出错: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="把漫画双页图片批量拆分为单页")
    parser.add_argument("input_dir", help="包含漫画图片的目录路径")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    if not input_dir.is_dir():
        print(f"错误: 目录 '{input_dir}' 不存在")
        return 1

    output_dir = input_dir.parent / f"{input_dir.name}_split"

    print(f"开始处理目录: {input_dir}")
    process_directory(input_dir, output_dir)
    print(f"处理完成，拆分后的图片保存在: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
