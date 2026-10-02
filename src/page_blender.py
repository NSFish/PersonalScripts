#!/usr/bin/env python3
"""图片裁剪与拼接：从图1 裁下一条边（宽度/高度 = number），贴到图2 的同一边上。

输出为图1 同目录下的 `result_<方向>_<number>.png`
（中间产物用无损 PNG，最终交给 primage 转 avif）。

示例: page_blender.py -u 300 image1.jpg image2.jpg
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

# 垂直方向按高度裁，水平方向按宽度裁
VERTICAL = ("up", "down")


def blend(img1: Image.Image, img2: Image.Image, direction: str, number: int) -> Image.Image:
    """把 img1 在 direction 那侧的 number 像素贴到 img2 的同一侧，返回新图。"""
    w, h = img1.size
    if img2.size != (w, h):
        raise ValueError(f"两张图片的尺寸必须完全相同：{img1.size} vs {img2.size}")
    if number <= 0:
        raise ValueError(f"裁剪尺寸必须为正数，当前: {number}")

    # number 是垂直方向的像素数还是水平方向的
    limit = h if direction in VERTICAL else w
    if number >= limit:
        axis = "高度" if direction in VERTICAL else "宽度"
        raise ValueError(f"当方向为 '{direction}' 时，数字必须小于图片{axis} ({limit})")

    if direction == "up":
        strip, pos = img1.crop((0, 0, w, number)), (0, 0)
    elif direction == "down":
        strip, pos = img1.crop((0, h - number, w, h)), (0, h - number)
    elif direction == "left":
        strip, pos = img1.crop((0, 0, number, h)), (0, 0)
    else:  # right
        strip, pos = img1.crop((w - number, 0, w, h)), (w - number, 0)

    result = img2.copy()
    result.paste(strip, pos)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="图片裁剪与拼接工具")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-u", "--up", action="store_true", help="向上裁剪拼接")
    group.add_argument("-d", "--down", action="store_true", help="向下裁剪拼接")
    group.add_argument("-l", "--left", action="store_true", help="向左裁剪拼接")
    group.add_argument("-r", "--right", action="store_true", help="向右裁剪拼接")
    parser.add_argument("number", type=int, help="裁剪尺寸（像素）")
    parser.add_argument("image1", help="第一张图片路径")
    parser.add_argument("image2", help="第二张图片路径")
    args = parser.parse_args()

    image1, image2 = Path(args.image1), Path(args.image2)
    for p in (image1, image2):
        if not p.is_file():
            print(f"错误：输入的图片不存在 → {p}")
            return 1

    direction = next(
        d for d, chosen in (
            ("up", args.up), ("down", args.down), ("left", args.left), ("right", args.right),
        ) if chosen
    )

    try:
        # 统一转 RGB，避免透明通道被丢弃
        with Image.open(image1) as im1, Image.open(image2) as im2:
            result = blend(im1.convert("RGB"), im2.convert("RGB"), direction, args.number)
    except Exception as e:
        print(f"错误：{e}")
        return 1

    output_path = image1.parent / f"result_{direction}_{args.number}.png"
    result.save(output_path)
    print(f"处理成功！结果已保存为: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
