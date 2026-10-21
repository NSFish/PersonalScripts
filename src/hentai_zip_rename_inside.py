#!/usr/bin/env python3
"""重新打包目录下的漫画压缩包（规范化内部结构与文件名，保留 macOS 标签）。

对目录里每个 .zip / .cbz：解压 → 若包内只有唯一顶层文件夹则改名与包名一致 → 重新压缩。
先写 `<包名>.tmp.<原扩展名>` 再原子替换原包，中途失败不会毁掉输入；
macOS 标签在替换后重新写回。输出扩展名与输入保持一致。
"""
import argparse
import shutil
import sys
import zipfile
from pathlib import Path

from _common import (
    copy_mac_tags,
    extract_zip,
    get_mac_tags,
    is_archive_file,
    is_hidden_part,
    iter_files,
    natural_key,
)

STALE_SUFFIX = ".tmp"  # 上次运行失败残留的临时包（<包名>.tmp.zip / .tmp.cbz），不作为输入处理


def is_stale(path: Path) -> bool:
    """是否为上次运行残留的临时包（扩展名前的名字以 .tmp 结尾）。"""
    return Path(path).stem.endswith(STALE_SUFFIX)


def rezip_folder(extract_dir: Path, zip_path: Path) -> None:
    """把 extract_dir 的内容压成 zip_path（排除隐藏文件与 .DS_Store / __MACOSX）。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in iter_files(extract_dir):
            zf.write(f, f.relative_to(extract_dir))


def normalize_inner_folder(extract_dir: Path, zip_name: str) -> None:
    """包内只有唯一顶层文件夹时，把它的名字改成与包名一致。"""
    items = [p for p in extract_dir.iterdir() if not is_hidden_part(p.name)]
    if len(items) != 1 or not items[0].is_dir():
        return
    inner = items[0]
    if inner.name != zip_name:
        inner.rename(extract_dir / zip_name)
        print(f"已重命名文件夹: {inner.name} -> {zip_name}")


def repack(zip_path: Path) -> None:
    """重新打包单个压缩包；失败抛异常由调用方汇总。"""
    # 标签必须在 replace 之前读出来：替换后原文件（连同标签）已经不存在了
    tags = get_mac_tags(zip_path)
    print(f"{zip_path.name} 标签: {', '.join(tags) if tags else '(无)'}")

    extract_dir = zip_path.with_name(f"{zip_path.stem}_tmp")
    if extract_dir.exists():
        shutil.rmtree(extract_dir)  # 清掉上次运行残留，避免混入新压缩包

    # 解压走 extract_zip：顺手修正缺 UTF-8 标记的中文条目名，坏包抛异常由调用方汇总
    extract_zip(zip_path, extract_dir)

    normalize_inner_folder(extract_dir, zip_path.stem)

    # 先写临时文件再原子替换，失败时原包不受影响；扩展名沿用原包（zip/cbz）
    stage_path = zip_path.with_name(f"{zip_path.stem}{STALE_SUFFIX}{zip_path.suffix}")
    try:
        rezip_folder(extract_dir, stage_path)
        if tags:
            copy_mac_tags(zip_path, stage_path)
        stage_path.replace(zip_path)
    finally:
        if stage_path.exists():
            stage_path.unlink()
        shutil.rmtree(extract_dir, ignore_errors=True)

    print(f"已生成新压缩包并写入标签: {zip_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="重新打包目录下的漫画压缩包（规范化内部结构并保留标签）")
    parser.add_argument("folder", help="装着 .zip / .cbz 的文件夹路径")
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"错误: 文件夹 '{folder}' 不存在")
        return 1

    archives = sorted(
        (p for p in folder.iterdir() if p.is_file() and is_archive_file(p) and not is_stale(p)),
        key=lambda p: natural_key(p.name),
    )
    if not archives:
        print(f"ℹ️ {folder} 内未找到 .zip / .cbz 压缩包")
        return 0

    failures = 0
    for archive in archives:
        try:
            repack(archive)
        except Exception as e:
            print(f"❌ {archive.name} 处理失败: {e}")
            failures += 1

    if failures:
        print(f"\n❌ 共 {failures} 个压缩包处理失败")
        return 1
    print("\n🎉 处理完毕！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
