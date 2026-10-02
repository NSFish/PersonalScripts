#!/usr/bin/env python3
"""电子书转 CBZ：mobi/epub → 解包 → 抽取图片 → 重新打包。

替代原 epub/shell script/ebook_2_zip.sh（Python 重写版）：

- .mobi：先用 Calibre 的 ebook-convert 转成 EPUB 再解包；
- .epub：直接解包；
- 漫画模式（默认开启）：只打包解包后的 image/images 目录，输出纯图片 .cbz
  （cbz 即改了扩展名的 zip，用 zipfile 标准库打包，ZIP_STORED 不重复压图）；
- 输出到输入文件的父目录，同名 .cbz 已存在时跳过（断点续跑）；
- 支持传文件夹：批量处理其中所有 .mobi/.epub。

依赖：转换 mobi 需要安装 Calibre（ebook-convert 在 PATH 或默认安装位置）。
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# Calibre 命令行的常见位置：PATH 之外再兜底 macOS 默认安装路径
EBOOK_CONVERT_FALLBACKS = (
    "/Applications/calibre.app/Contents/MacOS/ebook-convert",
    "/opt/homebrew/bin/ebook-convert",
    "/usr/local/bin/ebook-convert",
)

# epub 解包后常见图片目录名（按优先级）
IMAGE_DIR_NAMES = ("image", "images")

# 打包时排除的杂物
EXCLUDE_NAMES = (".DS_Store", "__MACOSX")


def find_ebook_convert() -> str | None:
    """定位 ebook-convert：先查 PATH，再查常见安装路径。"""
    found = shutil.which("ebook-convert")
    if found:
        return found
    for path in EBOOK_CONVERT_FALLBACKS:
        if Path(path).is_file():
            return path
    return None


def mobi_to_epub(src: Path, dst_epub: Path) -> None:
    """用 Calibre 的 ebook-convert 把 mobi 转成 epub。"""
    ebook_convert = find_ebook_convert()
    if ebook_convert is None:
        raise RuntimeError("找不到 ebook-convert，请先安装 Calibre")
    print("→ 转换为 EPUB (ebook-convert)...")
    r = subprocess.run(
        [ebook_convert, str(src), str(dst_epub)],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not dst_epub.exists():
        tail = "\n".join((r.stdout + r.stderr).splitlines()[-10:])
        raise RuntimeError(f"mobi 转 EPUB 失败:\n{tail}")


def unpack_input(src: Path, unpack_dir: Path) -> None:
    """把 .mobi/.epub 解包到 unpack_dir；mobi 先转成 epub 再解包。"""
    if src.suffix.lower() == ".epub":
        with zipfile.ZipFile(src) as zf:
            zf.extractall(unpack_dir)
        return

    epub_path = unpack_dir / f"{src.stem}.epub"
    mobi_to_epub(src, epub_path)
    with zipfile.ZipFile(epub_path) as zf:
        zf.extractall(unpack_dir / "content")


def find_image_dir(unpack_dir: Path) -> Path | None:
    """定位漫画图片目录：常见目录名优先，其次一级子目录。"""
    for name in IMAGE_DIR_NAMES:
        candidate = unpack_dir / name
        if candidate.is_dir():
            return candidate
    for sub in sorted(unpack_dir.iterdir()):
        if not sub.is_dir():
            continue
        for name in IMAGE_DIR_NAMES:
            candidate = sub / name
            if candidate.is_dir():
                return candidate
    return None


def iter_pack_files(base: Path) -> list[Path]:
    """递归收集要打包的文件，排除隐藏杂物，按包内相对路径排序。"""
    files = [
        p for p in base.rglob("*")
        if p.is_file()
        and not p.name.startswith(".")
        and p.name not in EXCLUDE_NAMES
        and "__MACOSX" not in p.parts
    ]
    return sorted(files, key=lambda p: p.relative_to(base).as_posix())


def pad(n: int, width: int) -> str:
    """把整数 n 零填充到 width 位。"""
    return str(n).zfill(width)


def sequential_names(files: list[Path]) -> dict[Path, str]:
    """按 chapter_pages_rename_by_order 的命名逻辑生成零填充序号。

    与该脚本一致：enumerate 从 0 起始，位宽 max(2, len(str(总数)))，
    保留原扩展名。源文件名序号有空洞（Calibre 去重/跳号），打包前
    统一重编成连续序号，避免阅读器页码映射缺页。
    """
    digit = max(2, len(str(len(files))))
    return {f: f"{pad(i, digit)}{f.suffix}" for i, f in enumerate(files)}


def pack_cbz(base: Path, dst: Path) -> None:
    """把 base 下全部文件打包为 dst，按顺序重命名为 1..N 零填充。"""
    files = iter_pack_files(base)
    if not files:
        raise RuntimeError(f"{base} 里没有可打包的文件")
    names = sequential_names(files)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_STORED) as zf:
        for f in files:
            zf.write(f, arcname=names[f])


def convert_one(src: Path, comic: bool) -> Path:
    """转换单个文件，返回输出的 cbz 路径；失败抛异常。"""
    dst = src.with_suffix(".cbz")
    if dst.exists():
        print(f"ℹ️ 已存在，跳过: {dst.name}")
        return dst

    try:
        with tempfile.TemporaryDirectory(prefix="ebook2cbz_") as tmp:
            unpack_dir = Path(tmp) / "unpack"
            unpack_dir.mkdir()
            unpack_input(src, unpack_dir)
            base = unpack_dir
            if comic:
                image_dir = find_image_dir(unpack_dir)
                if image_dir is None:
                    raise RuntimeError("无法找到图片目录 (image/images)")
                base = image_dir
            print(f"→ 打包 {len(iter_pack_files(base))} 个文件...")
            pack_cbz(base, dst)
    except Exception as e:
        if dst.exists():
            dst.unlink()
        raise RuntimeError(f"{src.name}: {e}") from e

    print(f"✅ 完成: {dst.name} ({dst.stat().st_size // 1024 // 1024} MB)")
    return dst


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="电子书(mobi/epub)转 CBZ：解包后抽取图片重新打包",
    )
    parser.add_argument("input", help="输入的 .mobi/.epub 文件，或装着它们的文件夹")
    parser.add_argument(
        "--no-comic", action="store_true",
        help="关闭漫画模式：打包解包后的全部内容（默认只打包 image/images 目录）",
    )
    args = parser.parse_args(argv)

    src = Path(args.input).expanduser().resolve()
    comic = not args.no_comic

    if src.is_file() and src.suffix.lower() in (".mobi", ".epub"):
        jobs = [src]
    elif src.is_dir():
        jobs = sorted(
            p for p in src.iterdir()
            if p.is_file() and p.suffix.lower() in (".mobi", ".epub")
        )
        if not jobs:
            print(f"ℹ️ {src} 下没有 .mobi/.epub 文件")
            return
    else:
        parser.error(f"输入必须是 .mobi/.epub 文件或文件夹: {src}")

    print(f"共 {len(jobs)} 个待处理文件（{'漫画' if comic else '完整'}模式）")
    ok = 0
    for job in jobs:
        print(f"\n=== {job.name} ===")
        try:
            convert_one(job, comic)
            ok += 1
        except Exception as e:
            print(f"❌ {e}")
    print(f"\n完成：{ok}/{len(jobs)}")
    if ok < len(jobs):
        sys.exit(1)


if __name__ == "__main__":
    main()
