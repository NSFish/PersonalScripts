#!/usr/bin/env python3
"""把指定目录下的每个子文件夹压缩为同名 .cbz（排除隐藏文件与 .DS_Store / __MACOSX）。

替代原 zip_all.sh：用 zipfile 标准库，不再依赖系统 zip。
包内保留 `<子文件夹名>/...` 的顶层目录结构，便于解压后仍是独立一册。

输出 .cbz 而非 .zip：这是漫画阅读器（Komga/Panels/YACReader 等）认的扩展名，
而 .cbz 就是改了名的 .zip，zipfile 直接写即可（见 _common.ARCHIVE_EXTS）。
要 .zip 用 `--ext zip`。
"""
import argparse
import sys
import zipfile
from pathlib import Path

from _common import iter_files


def zip_folder(folder: Path, parent_dir: Path, ext: str = "cbz") -> bool:
    """把 folder 压成 parent_dir/<folder.name>.<ext>，成功返回 True。"""
    zip_path = parent_dir / f"{folder.name}.{ext}"
    if zip_path.exists():
        print(f"⚠️ 跳过 '{folder.name}'：已存在同名压缩包")
        return False

    print(f"正在压缩: {folder.name}")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in iter_files(folder):
                zf.write(f, f.relative_to(parent_dir))
    except Exception as e:
        print(f"❌ 压缩失败: {folder.name} ({e})")
        return False

    print(f"✅ 已创建: {folder.name}.{ext}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="把每个子文件夹压缩为同名 .cbz")
    parser.add_argument("parent_dir", help="装着子文件夹的目标文件夹路径")
    parser.add_argument("--ext", default="cbz", choices=["cbz", "zip"],
                        help="输出扩展名（默认 cbz）")
    args = parser.parse_args()

    parent_dir = Path(args.parent_dir).resolve()
    if not parent_dir.is_dir():
        print(f"错误：文件夹 '{parent_dir}' 不存在。")
        return 1

    folders = sorted(p for p in parent_dir.iterdir() if p.is_dir())
    if not folders:
        print(f"ℹ️ {parent_dir} 内没有子文件夹可压缩")
        return 0

    for folder in folders:
        zip_folder(folder, parent_dir, args.ext)

    print("操作完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
