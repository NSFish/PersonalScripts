#!/usr/bin/env python3
"""递归把目录下所有 .jpeg 图片扩展名改为 .jpg。

替代原 jpeg_2_jpg.sh：纯 pathlib 逻辑，跨平台。
"""
import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="递归把 .jpeg 改名为 .jpg")
    parser.add_argument("target_dir", help="目标目录")
    args = parser.parse_args()

    target = Path(args.target_dir).resolve()
    if not target.is_dir():
        print("错误：请提供目标目录路径")
        sys.exit(1)

    count = 0
    for file in sorted(target.rglob("*")):
        if not file.is_file() or file.suffix.lower() != ".jpeg":
            continue
        new_path = file.with_suffix(".jpg")
        if new_path.exists():
            print(f"跳过(已存在): {file.name}")
            continue
        file.rename(new_path)
        rel = file.relative_to(target)
        print(f"{rel} -> {rel.with_suffix('.jpg')}")
        count += 1

    print(f"操作完成！共修改 {count} 个文件")


if __name__ == "__main__":
    main()
