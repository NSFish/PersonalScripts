#!/usr/bin/env python3
"""递归解压指定目录下的 .zip/.cbz，把其中的图片抽到以压缩包命名的子文件夹。

替代原 unzip_all.sh：用 zipfile 标准库，不再依赖系统 unzip。
"""
import sys
from pathlib import Path

import zipfile

from _common import is_image_file


def main() -> None:
    if len(sys.argv) != 2:
        print("使用方法: unzip_all.py <文件夹路径>")
        sys.exit(1)

    input_dir = Path(sys.argv[1]).resolve()
    if not input_dir.is_dir():
        print(f"错误: 文件夹 '{input_dir}' 不存在")
        sys.exit(1)

    archives = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".zip", ".cbz")
    )

    for file in archives:
        base_name = file.stem
        print(f"正在处理: {file.name}")

        try:
            with zipfile.ZipFile(file) as zf:
                names = zf.namelist()
                target = input_dir / base_name
                target.mkdir(parents=True, exist_ok=True)
                moved = 0
                for name in names:
                    if name.endswith("/") or name.endswith("\\"):
                        continue
                    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                    if not is_image_file(name):
                        continue
                    # 取压缩包内相对路径的最后一段作为文件名，避免路径穿越
                    dest_name = Path(name).name
                    if not dest_name:
                        continue
                    dest = target / dest_name
                    with zf.open(name) as src, open(dest, "wb") as out:
                        out.write(src.read())
                    moved += 1
        except zipfile.BadZipFile as e:
            print(f"❌ 解压 {file.name} 失败: {str(e)[:100]}")
            continue

        if moved > 0:
            print(f"✅ 解压 {file.name} 成功 (移动了 {moved} 张图片)")
        else:
            target.rmdir() if (target.is_dir() and not any(target.iterdir())) else None
            print(f"❌ 解压 {file.name} 失败: 未找到支持的图片文件")

    print("处理完成！")


if __name__ == "__main__":
    main()
