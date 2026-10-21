#!/usr/bin/env python3
"""解压指定目录下的 .zip/.cbz，把其中的图片抽到以压缩包命名的子文件夹。

替代原 unzip_all.sh：用 zipfile 标准库，不再依赖系统 unzip。
只处理所给目录最外层的压缩包；包内的目录结构会被拍平，
同名文件先到先得（后者打印警告并跳过），避免路径穿越。
"""
import argparse
import sys
import zipfile
from pathlib import Path

from _common import fix_zip_filename, is_archive_file, is_image_file


def extract_archive(archive: Path, input_dir: Path) -> int:
    """把单个压缩包里的图片抽到 input_dir/<包名>/，返回抽出的张数。"""
    print(f"正在处理: {archive.name}")
    target = input_dir / archive.stem
    moved = 0
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                name = fix_zip_filename(info)  # 兼容缺 UTF-8 标记的中文包
                if name.endswith(("/", "\\")):
                    continue
                if not is_image_file(name):
                    continue
                # 只取包内相对路径的最后一段作为文件名，避免路径穿越
                dest_name = Path(name).name
                if not dest_name:
                    continue
                dest = target / dest_name
                if dest.exists():
                    print(f"⚠️ 跳过重名文件: {dest_name}")
                    continue
                # 有图可写时才建目录：没图片的坏包不会留下空文件夹
                target.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src:
                    dest.write_bytes(src.read())
                moved += 1
    except zipfile.BadZipFile as e:
        print(f"❌ 解压 {archive.name} 失败: {str(e)[:100]}")
        if target.is_dir() and not any(target.iterdir()):
            target.rmdir()
        return 0

    if moved == 0:
        print(f"❌ 解压 {archive.name} 失败: 未找到支持的图片文件")
        return 0

    print(f"✅ 解压 {archive.name} 成功 (移动了 {moved} 张图片)")
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description="解压目录下的 .zip/.cbz 并抽出图片")
    parser.add_argument("input_dir", help="装着压缩包的文件夹路径")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    if not input_dir.is_dir():
        print(f"错误: 文件夹 '{input_dir}' 不存在")
        sys.exit(1)

    archives = [p for p in sorted(input_dir.iterdir()) if p.is_file() and is_archive_file(p)]
    if not archives:
        print(f"ℹ️ {input_dir} 内未找到 .zip/.cbz 压缩包")
        return

    for archive in archives:
        extract_archive(archive, input_dir)

    print("处理完成！")


if __name__ == "__main__":
    main()
