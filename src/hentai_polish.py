#!/usr/bin/env python3
"""统一处理本子漫画：重命名（纯数字零填充）→ 转 AVIF → 打包 CBZ。

用法: python hentai_polish.py <输入路径>

输入路径可以是：
- 图片文件夹（含子文件夹：递归收集后按相对路径自然排序，输出时拍平成纯数字名）；
- 单张图片（视为只有 1 页的本子）；
- 单个漫画压缩包（.zip/.cbz）；
- 装着压缩包的文件夹（批量处理，每个包输出一个 .cbz，散图单独打成一包）。

命名规则：按自然排序编号为 1..N，零填充到与总数同宽
（100 张 → 001..100，12 张 → 01..12，9 张 → 1..9）。
输出：统一放在输入路径父目录的 `result/` 里，均为干净名，不加后缀——
单个输入（文件夹/单张图/单个包）→ `result/<原名>.cbz`；
批量文件夹 → `result/` 内每个包一个 `<包名>.cbz`，散图单独打成 `<文件夹名>.cbz`。
压缩包输入的 macOS 标签会复制到输出包。
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from _common import (
    OUTPUT_DIR_NAME,
    copy_mac_tags,
    extract_zip,
    is_archive_file,
    is_image_file,
    iter_files,
    list_archives,
    list_images,
    natural_key,
    pad,
    prepare_result_dir,
    run_primage,
)


def collect_images(root: Path) -> tuple[list[Path], int]:
    """递归收集 root 下的图片，按相对路径自然排序；返回（图片列表，跳过的非图片文件数）。"""
    imgs, skipped = [], 0
    for p in iter_files(root):  # 已排除隐藏文件与 .DS_Store / __MACOSX
        if is_image_file(p):
            imgs.append(p)
        else:
            skipped += 1
    return imgs, skipped


def polish_book(sources: list[Path], dst_cbz: Path) -> bool:
    """把已排好序的图片列表整理成一本 cbz：复制到临时目录并重命名为 001..N，转 avif，打包。

    成功返回 True；有图片转换失败则不输出（删除残留），返回 False。
    """
    total = len(sources)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for i, src in enumerate(sources, 1):
            shutil.copy2(src, tmpdir / f"{pad(i, len(str(total)))}{src.suffix.lower()}")
        staged = sorted(tmpdir.iterdir(), key=lambda p: natural_key(p.name))
        failures = 0
        # staged 与 sources 一一对应（零填充命名排序后顺序不变），log 里同时打出原名方便核对
        for i, (orig, p) in enumerate(zip(sources, staged), 1):
            target = p.with_suffix(".avif")
            if p.suffix.lower() == ".avif":
                print(f"[{i}/{total}] ⏭️ 已是 avif，直接采用: {orig.name} -> {target.name}")
                continue
            try:
                run_primage(p, target, "avif")
            except subprocess.CalledProcessError as e:
                print(f"[{i}/{total}] ❌ 转换失败: {orig.name}，错误: {e.stderr}")
                failures += 1
                continue
            p.unlink()
            print(f"[{i}/{total}] ✅ {orig.name} -> {target.name}")
        if failures:
            return False
        if dst_cbz.exists():
            dst_cbz.unlink()
        with zipfile.ZipFile(dst_cbz, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(tmpdir.iterdir(), key=lambda x: natural_key(x.name)):
                zf.write(p, p.name)
    print(f"✅ 打包完成: {dst_cbz}")
    return True


def polish_from_dir(src_dir: Path, book_name: str, dst_cbz: Path) -> bool:
    """从图片文件夹整理出一本 cbz；无图片返回 False。"""
    imgs, skipped = collect_images(src_dir)
    if not imgs:
        print(f"❌ {src_dir} 内未找到任何支持的图片")
        return False
    print(f"📖 正在整理本子: {book_name}（共 {len(imgs)} 张图片 → {dst_cbz.name}）")
    if skipped:
        print(f"ℹ️ 跳过 {skipped} 个非图片文件")
    return polish_book(imgs, dst_cbz)


def polish_from_archive(src_zip: Path, book_name: str, dst_cbz: Path) -> bool:
    """从单个压缩包整理出一本 cbz；无图片返回 False。成功时复制源包标签。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        extract_zip(src_zip, tmpdir)
        imgs, skipped = collect_images(tmpdir)
        if not imgs:
            print(f"❌ {src_zip.name} 内未找到任何支持的图片")
            return False
        print(f"📖 正在整理本子: {book_name}（共 {len(imgs)} 张图片 → {dst_cbz.name}）")
        if skipped:
            print(f"ℹ️ 跳过 {skipped} 个非图片文件")
        ok = polish_book(imgs, dst_cbz)
    if ok:
        copy_mac_tags(src_zip, dst_cbz)
    return ok


def polish_batch(src_dir: Path) -> int:
    """批量整理文件夹内的压缩包（散图单独打成一包）；输出到输入父目录的 `result/`。返回失败数。"""
    out_dir = src_dir.parent / OUTPUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 正在处理文件夹: {src_dir}（输出到 {out_dir}）")
    failures = 0
    archives = list_archives(src_dir)
    print(f"📦 共找到 {len(archives)} 个压缩包待处理")
    for i, src in enumerate(archives, 1):
        dst = out_dir / f"{src.stem}.cbz"
        print(f"===== [{i}/{len(archives)}] =====")
        if not polish_from_archive(src, src.name, dst):
            failures += 1
    loose = list_images(src_dir)
    if loose:
        print("===== [散图] =====")
        dst = out_dir / f"{src_dir.name}.cbz"
        print(f"📖 正在整理本子: 散图（共 {len(loose)} 张图片 → {dst.name}）")
        if not polish_book(loose, dst):
            failures += 1
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="统一处理本子漫画：重命名（001..N）→ 转 AVIF → 打包 CBZ"
    )
    parser.add_argument("input_path", help="输入路径（图片/图片文件夹/单个.zip/.cbz/批量包文件夹）")
    args = parser.parse_args(argv)
    src = Path(args.input_path)

    if not src.exists():
        print(f"❌ 输入路径不存在: {src}")
        return 1

    result_dir = prepare_result_dir(src)

    if src.is_file():
        dst = result_dir / f"{src.stem}.cbz"
        if is_archive_file(src):
            ok = polish_from_archive(src, src.name, dst)
        elif is_image_file(src):
            print(f"📖 正在整理本子: {src.name}（共 1 张图片 → {dst.name}）")
            ok = polish_book([src], dst)
            if ok:
                copy_mac_tags(src, dst)
        else:
            print(f"❌ 不支持的文件类型: {src}（仅支持图片与 .zip/.cbz）")
            return 1
        if not ok:
            print(f"\n❌ 处理失败: {src.name}")
            return 1
        print("\n🎉 处理完毕！")
        return 0

    archives = list_archives(src)
    has_images = any(is_image_file(p) for p in iter_files(src))
    if archives:
        failures = polish_batch(src)
    elif has_images:
        ok = polish_from_dir(src, src.name, result_dir / f"{src.name}.cbz")
        failures = 0 if ok else 1
    else:
        print(f"❌ {src} 内未找到任何支持的图片或压缩包")
        return 1
    if failures:
        print(f"\n❌ 共 {failures} 本处理失败")
        return 1
    print("\n🎉 处理完毕！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
