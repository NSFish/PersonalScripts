#!/usr/bin/env python3
"""按文件名倒数第二段下划线内容，把图片归类进对应子文件夹。

替代原 pages_organize_into_chapters.sh：纯 pathlib 逻辑。
如 abc_12_34.jpg -> 抽到子文件夹 "12/"。
"""
import argparse
import sys
from pathlib import Path

from _common import is_image_file


def main() -> None:
    parser = argparse.ArgumentParser(description="按文件名下划线分段归类图片到子文件夹")
    parser.add_argument("folder_path", help="文件夹路径")
    args = parser.parse_args()

    folder = Path(args.folder_path).resolve()
    if not folder.is_dir():
        print(f"错误: 指定的文件夹 {folder} 不存在。")
        sys.exit(1)

    for file in sorted(folder.iterdir()):
        if not file.is_file():
            continue
        if not is_image_file(file):
            continue

        parts = file.name.rsplit("_")
        if len(parts) >= 3:
            subfolder = parts[-2]
            dest_dir = folder / subfolder
            dest_dir.mkdir(parents=True, exist_ok=True)
            file.rename(dest_dir / file.name)
            print(f"已移动: {file.name} → {subfolder}/")
        else:
            print(f"警告: 无法从 '{file.name}' 中提取子文件夹名（格式不符合要求）")


if __name__ == "__main__":
    main()
