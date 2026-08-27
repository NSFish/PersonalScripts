#!/usr/bin/env python3
"""单张图片格式转换（primage 封装）。

替代原 primage_wrapper.sh：检查 primage 是否安装，目标扩展名一致则跳过，
-jpg 映射为 jpeg，-q 90 保证高质量。
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="单张图片格式转换(primage 封装)")
    parser.add_argument("image_path", help="图片路径")
    parser.add_argument("target_ext", nargs="?", default="jpg", help="目标扩展名(默认 jpg，无需加点)")
    args = parser.parse_args()

    image = Path(args.image_path).resolve()
    if not image.is_file():
        print(f"错误: 图片文件不存在 → {image}")
        sys.exit(1)

    target_ext = args.target_ext.lstrip(".").lower()
    if not target_ext:
        print("错误: 目标扩展名不能为空！")
        sys.exit(1)

    original_ext = image.suffix.lower().lstrip(".")
    if original_ext == target_ext:
        print(f"ℹ️  原图扩展名（{original_ext}）与目标扩展名（{target_ext}）一致，无需转换")
        sys.exit(0)

    if not shutil.which("primage"):
        print("错误: 未检测到 primage 命令，请先安装！")
        print("  brew install primage")
        sys.exit(1)

    new_path = image.with_suffix("." + target_ext)
    if new_path.exists():
        if sys.stdin.isatty():
            confirm = input(f"警告: 目标文件已存在 → {new_path}，是否覆盖？(y/N) ").strip()
            if confirm.lower() != "y":
                print("转换取消")
                sys.exit(0)
        else:
            print(f"转换取消: 目标文件已存在 → {new_path}")
            sys.exit(0)

    primage_fmt = "jpeg" if target_ext == "jpg" else target_ext
    print(f"正在转换: {image} → {new_path}")
    try:
        subprocess.run(
            ["primage", "-f", primage_fmt, "-q", "90", "-o", str(new_path), str(image)],
            check=True,
        )
    except subprocess.CalledProcessError:
        print("❌ 转换失败！")
        sys.exit(1)

    print(f"✅ 转换成功！生成文件：{new_path}")


if __name__ == "__main__":
    main()
