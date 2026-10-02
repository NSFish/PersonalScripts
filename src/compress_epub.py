#!/usr/bin/env python3
"""把一个已备齐内容的文件夹打包成合规 EPUB。

替代原 shell script/compress_epub.sh：用 zipfile 标准库，不再依赖系统 zip。

EPUB 规范要求 mimetype 必须**不压缩**且是包内**第一个条目**，所以分两步：
先写 mimetype（ZIP_STORED），再递归写入 META-INF 与 OEBPS（ZIP_DEFLATED）。

输出到源文件夹的父目录：<文件夹名>.epub。
"""
import argparse
import sys
import zipfile
from pathlib import Path

# EPUB 规范要求的必备文件
REQUIRED_FILES = ("mimetype", "META-INF/container.xml")
# mimetype 之后要打包的顶层内容（规范要求的目录结构）
CONTENT_DIRS = ("META-INF", "OEBPS")


def iter_entries(base: Path):
    """深度优先遍历 base：进目录先写目录项，再写其直属文件，然后递归子目录。

    与 `zip -r` 的遍历顺序一致，保证输出与旧 shell 版等价。
    产出 (路径, arcname)，arcname 以 / 结尾表示目录条目。
    """
    arc_prefix = base.name

    def walk(d: Path, rel: str):
        arc = f"{rel}{d.name}/" if rel else f"{d.name}/"
        yield d, arc
        for f in sorted((p for p in d.iterdir() if p.is_file()),
                        key=lambda p: p.name):
            yield f, f"{arc}{f.name}"
        for sub in sorted((p for p in d.iterdir() if p.is_dir()),
                          key=lambda p: p.name):
            yield from walk(sub, arc)

    # 先写 base 自身的目录项，再写其直属文件，最后递归子目录
    yield base, f"{arc_prefix}/"
    for f in sorted((p for p in base.iterdir() if p.is_file()),
                    key=lambda p: p.name):
        yield f, f"{arc_prefix}/{f.name}"
    for sub in sorted((p for p in base.iterdir() if p.is_dir()),
                      key=lambda p: p.name):
        yield from walk(sub, f"{arc_prefix}/")


def compress_epub(target_dir: Path) -> Path:
    """把 target_dir 打包为父目录下的 <文件夹名>.epub，返回输出路径。"""
    for rel in REQUIRED_FILES:
        if not (target_dir / rel).is_file():
            raise FileNotFoundError(f"缺少EPUB必需文件 '{target_dir / rel}'")

    dst = target_dir.parent / f"{target_dir.name}.epub"
    if dst.exists():
        dst.unlink()

    with zipfile.ZipFile(dst, "w") as zf:
        # 第 1 步：mimetype 单独存、不压缩、排第一
        mimetype = target_dir / "mimetype"
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0o644 << 16
        zf.writestr(info, mimetype.read_bytes())

        # 第 2 步：其余内容递归压缩（缺失的目录跳过，与旧脚本 zip 行为一致）
        for name in CONTENT_DIRS:
            root = target_dir / name
            if not root.is_dir():
                print(f"⚠️ 未找到目录 '{name}'，已跳过")
                continue
            for path, arc in iter_entries(root):
                zf.write(path, arcname=arc, compress_type=zipfile.ZIP_DEFLATED)
    return dst


def main() -> None:
    parser = argparse.ArgumentParser(description="把文件夹打包成合规 EPUB（mimetype 不压缩且置首）")
    parser.add_argument("target_dir", help="源文件夹路径（内含 mimetype、META-INF、OEBPS）")
    args = parser.parse_args()

    target = Path(args.target_dir).expanduser().resolve()
    if not target.is_dir():
        print(f"错误：文件夹 '{target}' 不存在")
        sys.exit(1)

    try:
        dst = compress_epub(target)
    except FileNotFoundError as e:
        print(f"错误：{e}")
        sys.exit(1)

    print(f"✅ EPUB生成成功！路径：{dst}")
    print("💡 已确保 mimetype 未压缩且是第一个条目，且内容直接在 EPUB 根目录（无外层文件夹）。")


if __name__ == "__main__":
    main()
