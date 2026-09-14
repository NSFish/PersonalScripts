#!/usr/bin/env python3
"""水平或垂直拼接两张图片（韩漫拼接）。

输出到第一张图片所在目录，文件名 `merged_<图1名>_<图2名>.png`
（中间产物用无损 PNG，最终交给 primage 转 avif）。
"""
import argparse
import sys
from pathlib import Path

from PIL import Image


def merge_images(img1: Image.Image, img2: Image.Image, direction: str) -> Image.Image:
    """按 direction 拼两张已转为 RGB 的图；尺寸不匹配抛 ValueError。"""
    if direction == "horizontal":
        if img1.height != img2.height:
            raise ValueError(
                f"水平拼接要求图片高度一致，当前高度分别为：{img1.height}px 和 {img2.height}px"
            )
        canvas = Image.new("RGB", (img1.width + img2.width, img1.height))
        canvas.paste(img2, (img1.width, 0))
    else:
        if img1.width != img2.width:
            raise ValueError(
                f"垂直拼接要求图片宽度一致，当前宽度分别为：{img1.width}px 和 {img2.width}px"
            )
        canvas = Image.new("RGB", (img1.width, img1.height + img2.height))
        canvas.paste(img2, (0, img1.height))
    canvas.paste(img1, (0, 0))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description="水平或垂直拼接图片")
    direction_group = parser.add_mutually_exclusive_group(required=True)
    direction_group.add_argument("-H", "--horizontal", action="store_true", help="水平拼接（需图片高度一致）")
    direction_group.add_argument("-V", "--vertical", action="store_true", help="垂直拼接（需图片宽度一致）")
    parser.add_argument("image1", help="第一张图片路径")
    parser.add_argument("image2", help="第二张图片路径")
    args = parser.parse_args()

    image1, image2 = Path(args.image1), Path(args.image2)
    for p in (image1, image2):
        if not p.is_file():
            print(f"错误：输入的图片不存在 → {p}")
            return 1

    direction = "horizontal" if args.horizontal else "vertical"
    try:
        # 统一转 RGB，避免透明通道被丢弃
        with Image.open(image1) as im1, Image.open(image2) as im2:
            merged = merge_images(im1.convert("RGB"), im2.convert("RGB"), direction)
    except Exception as e:
        print(f"错误：{e}")
        return 1

    output_path = image1.parent / f"merged_{image1.name}_{image2.name}.png"
    merged.save(output_path)
    print(f"拼接成功！图片已保存至：{output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
