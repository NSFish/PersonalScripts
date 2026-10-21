#!/usr/bin/env python3
"""图片格式万能转换入口（jpeg/png/webp/avif）。

用法: python convert_image_format_to.py <输出格式> <输入路径>

输入路径可以是：
- 单张图片 → `result/<同名新格式文件>`；
- 图片文件夹（仅最外层文件）→ `result/<文件夹名>/`；
- 单个漫画压缩包（.zip/.cbz）→ `result/<包名>.cbz`，保留包内目录结构；
- 装着压缩包的文件夹 → 批量转换到 `result/`（每个包一个 `<包名>.cbz` + 最外层散图）。

`result/` 建在输入路径的父目录下；输出均为干净名，不加格式后缀。
质量规则见 _common.primage_quality：avif 用 -q 60，其余用 -q 90。
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
    VALID_OUTPUT_FORMATS,
    copy_mac_tags,
    extract_zip,
    is_archive_file,
    is_image_file,
    iter_files,
    list_archives,
    list_images,
    prepare_result_dir,
    run_primage,
)


def _target_suffix(out_format: str) -> str:
    """目标格式对应的文件后缀（jpg/jpeg 统一为 .jpg）。"""
    fmt = out_format.lower()
    return ".jpg" if fmt in ("jpg", "jpeg") else f".{fmt}"


def convert_single_image(src: Path, dst: Path, out_format: str, progress: str = "") -> None:
    """转单张图片；已是目标格式则直接复制。失败抛 CalledProcessError。

    progress: 进度前缀，如 "[3/20] "，为空则不显示进度。
    """
    if src.suffix.lower() == _target_suffix(out_format):
        shutil.copy2(src, dst)
        print(f"{progress}⏭️ 已是{out_format}格式，直接复制: {src} -> {dst}")
        return
    run_primage(src, dst, out_format)
    print(f"{progress}✅ 转换成功: {src} -> {dst}")


def convert_image_dir(src_dir: Path, dst_dir: Path, out_format: str) -> int:
    """转图片文件夹最外层图片；返回失败数。"""
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True)
    files = list_images(src_dir)
    if not files:
        print(f"ℹ️ {src_dir} 内未找到任何支持的图片，输出空文件夹")
        return 0
    print(f"📁 正在处理文件夹: {src_dir}（共 {len(files)} 张图片 → {dst_dir}）")
    target = _target_suffix(out_format)
    failures = 0
    for i, src in enumerate(files, 1):
        dst = dst_dir / f"{src.stem}{target}"
        try:
            convert_single_image(src, dst, out_format, progress=f"[{i}/{len(files)}] ")
        except subprocess.CalledProcessError as e:
            print(f"[{i}/{len(files)}] ❌ 转换失败: {src.name}，错误: {e.stderr}")
            failures += 1
    return failures


def convert_single_archive(src_zip: Path, dst_zip: Path, out_format: str, tag: str = "") -> str:
    """转单个漫画包，保留包内目录结构。

    tag: 批量进度前缀，如 "[2/5] "，为空则不显示。
    返回 'converted'（已转换）或 'copied'（包内已全是目标格式，直接复制）。
    包内无图片抛 ValueError；primage 失败抛 CalledProcessError（已打印失败图名）。
    """
    target = _target_suffix(out_format)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        extract_zip(src_zip, tmpdir)
        imgs = [p for p in iter_files(tmpdir) if is_image_file(p)]
        if not imgs:
            raise ValueError(f"{src_zip.name} 内未找到任何支持的图片")
        if all(p.suffix.lower() == target for p in imgs):
            shutil.copy2(src_zip, dst_zip)
            print(f"{tag}ℹ️ {src_zip.name} 内全是{out_format}格式，直接复制")
            copy_mac_tags(src_zip, dst_zip)
            return "copied"
        print(f"{tag}📦 正在处理压缩包: {src_zip.name}（共 {len(imgs)} 张图片 → {dst_zip.name}）")
        for i, img in enumerate(imgs, 1):
            rel = img.relative_to(tmpdir)
            if img.suffix.lower() == target:
                print(f"{tag}[{i}/{len(imgs)}] ⏭️ 已是{out_format}格式，跳过: {rel}")
                continue
            try:
                run_primage(img, img.with_suffix(target), out_format)
            except subprocess.CalledProcessError as e:
                print(f"{tag}[{i}/{len(imgs)}] ❌ 转换失败: {rel}，错误: {e.stderr}")
                raise
            img.unlink()
            print(f"{tag}[{i}/{len(imgs)}] ✅ {rel} -> {rel.with_suffix(target)}")
        if dst_zip.exists():
            dst_zip.unlink()
        with zipfile.ZipFile(dst_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in iter_files(tmpdir):
                zf.write(p, p.relative_to(tmpdir))
    copy_mac_tags(src_zip, dst_zip)
    print(f"✅ 打包完成: {dst_zip}")
    return "converted"


def convert_archives_batch(src_dir: Path, out_format: str) -> int:
    """批量转文件夹内的压缩包，顺手转最外层散图；输出到输入父目录的 `result/`。返回失败数。"""
    out_dir = src_dir.parent / OUTPUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 正在处理文件夹: {src_dir}（输出到 {out_dir}）")
    failures = 0
    archives = list_archives(src_dir)
    if archives:
        print(f"📦 共找到 {len(archives)} 个压缩包待处理")
    for i, src in enumerate(archives, 1):
        dst = out_dir / f"{src.stem}.cbz"
        try:
            convert_single_archive(src, dst, out_format, tag=f"[{i}/{len(archives)}] ")
        except ValueError as e:
            print(f"[{i}/{len(archives)}] ❌ {e}")
            failures += 1
        except subprocess.CalledProcessError as e:
            print(f"[{i}/{len(archives)}] ❌ {src.name} 处理中断: {e.stderr}")
            failures += 1
    loose = list_images(src_dir)
    if loose:
        print(f"🖼️ 文件夹内另有 {len(loose)} 张散图，一并转换")
    target = _target_suffix(out_format)
    for i, src in enumerate(loose, 1):
        dst = out_dir / f"{src.stem}{target}"
        try:
            convert_single_image(src, dst, out_format, progress=f"[散图 {i}/{len(loose)}] ")
        except subprocess.CalledProcessError as e:
            print(f"[散图 {i}/{len(loose)}] ❌ 转换失败: {src.name}，错误: {e.stderr}")
            failures += 1
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="图片格式万能转换：单张图/图片文件夹/单个.zip/.cbz/批量包文件夹"
    )
    parser.add_argument("out_format", choices=list(VALID_OUTPUT_FORMATS), help="目标格式")
    parser.add_argument("input_path", help="输入路径（文件或文件夹）")
    args = parser.parse_args(argv)
    out_format = args.out_format.lower()
    src = Path(args.input_path)

    if not src.exists():
        print(f"❌ 输入路径不存在: {src}")
        return 1

    result_dir = prepare_result_dir(src)

    if src.is_file():
        if is_archive_file(src):
            dst = result_dir / f"{src.stem}.cbz"
            try:
                convert_single_archive(src, dst, out_format)
            except ValueError as e:
                print(f"❌ {e}")
                return 1
            except subprocess.CalledProcessError as e:
                print(f"❌ 转换失败: {e.stderr}")
                return 1
            return 0
        if is_image_file(src):
            dst = result_dir / f"{src.stem}{_target_suffix(out_format)}"
            if dst.exists():
                # result/ 是可重建的输出目录，同名就覆盖，与文件夹分支的重建行为一致
                print(f"ℹ️ 覆盖已有输出: {dst}")
            print(f"🖼️ 正在处理图片: {src} → {dst}")
            try:
                convert_single_image(src, dst, out_format)
            except subprocess.CalledProcessError as e:
                print(f"❌ 转换失败: {e.stderr}")
                return 1
            return 0
        print(f"❌ 不支持的文件类型: {src}（仅支持图片与 .zip/.cbz）")
        return 1

    archives, images = list_archives(src), list_images(src)
    if archives:
        failures = convert_archives_batch(src, out_format)
    elif images:
        failures = convert_image_dir(src, result_dir / src.name, out_format)
    else:
        print(f"❌ {src} 内未找到任何支持的图片或压缩包")
        return 1
    if failures:
        print(f"\n❌ 共 {failures} 处转换失败")
        return 1
    print("\n🎉 处理完毕！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
