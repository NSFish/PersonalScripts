#!/usr/bin/env python3
"""把指定目录下的每个子文件夹压缩为同名 .zip（排除 .DS_Store / __MACOSX）。

替代原 zip_all.sh：用 zipfile 标准库，不再依赖系统 zip。
"""
import sys
import zipfile
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        print("错误：请提供目标文件夹路径作为参数。")
        print("用法：zip_all.py /目标/文件夹路径")
        sys.exit(1)

    parent_dir = Path(sys.argv[1]).resolve()
    if not parent_dir.is_dir():
        print(f"错误：文件夹 '{parent_dir}' 不存在。")
        sys.exit(1)

    for folder in sorted(p for p in parent_dir.iterdir() if p.is_dir()):
        folder_name = folder.name
        zip_path = parent_dir / f"{folder_name}.zip"

        if zip_path.exists():
            print(f"⚠️ 跳过 '{folder_name}'：已存在同名压缩包")
            continue

        print(f"正在压缩: {folder_name}")
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(folder.rglob("*")):
                    if not f.is_file():
                        continue
                    if f.name == ".DS_Store" or "__MACOSX" in f.parts:
                        continue
                    arcname = f.relative_to(parent_dir)
                    zf.write(f, arcname)
        except Exception as e:
            print(f"❌ 压缩失败: {folder_name} ({e})")
            continue

        print(f"✅ 已创建: {folder_name}.zip")

    print("操作完成！")


if __name__ == "__main__":
    main()
