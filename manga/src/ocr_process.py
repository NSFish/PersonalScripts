#!/usr/bin/env python3
"""递归对子目录中的图片做 OCR，结果存为 JSON。

替代原 ocr_process.sh：调用仓库根目录的 macos-vision-ocr-arm64 二进制，
输出到 <父目录的父目录>/<输入目录名>_ocr_result/。不再依赖 jq。
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REC_LANGS = "zh-Hans,zh-Hant,en-US"
OCR_BIN = Path(__file__).resolve().parents[2] / "macos-vision-ocr-arm64"


def check_dependencies() -> None:
    if not OCR_BIN.exists() or not os.access(str(OCR_BIN), os.X_OK):
        print(f"错误: 未找到 macos-vision-ocr-arm64（查找路径: {OCR_BIN}）")
        print("请确保仓库根目录下存在该二进制（LFS 已拉取）。")
        sys.exit(1)
    try:
        out = subprocess.run([str(OCR_BIN), "--help"], capture_output=True, text=True)
    except Exception:
        out = None
    if out is None or "--img-dir" not in out.stdout + out.stderr:
        print("错误: OCR 工具不支持批量模式 (缺少 --img-dir 参数)")
        sys.exit(1)
    print("✅ 所有依赖已安装并支持批量模式")


def main() -> None:
    parser = argparse.ArgumentParser(description="图片 OCR 处理器")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细处理信息")
    parser.add_argument("parent_dir", help="父文件夹路径")
    args = parser.parse_args()

    parent_dir = Path(args.parent_dir).resolve()
    if not parent_dir.is_dir():
        print(f"错误: 文件夹不存在: {parent_dir}")
        sys.exit(1)

    check_dependencies()

    output_base = parent_dir.parent
    output_dir = output_base / f"{parent_dir.name}_ocr_result"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    subdirs = sorted(p for p in parent_dir.iterdir() if p.is_dir())
    total_dirs = len(subdirs)
    if total_dirs == 0:
        print(f"❌ 在 {parent_dir} 中找不到子目录")
        sys.exit(1)

    print(f"📁 创建输出目录: {output_dir}")
    print(f"✅ 找到 {total_dirs} 个子目录")

    start = time.time()
    for processed, sub in enumerate(subdirs, 1):
        print(f"🔄 处理进度: {processed}/{total_dirs} - {sub.name}")
        sub_output_dir = output_dir / sub.name
        sub_output_dir.mkdir(parents=True, exist_ok=True)
        if args.verbose:
            print(f"   运行批量 OCR: {OCR_BIN} --img-dir {sub} --output-dir {sub_output_dir} --rec-langs {REC_LANGS}")
        proc = subprocess.run(
            [str(OCR_BIN), "--img-dir", str(sub), "--output-dir", str(sub_output_dir), "--rec-langs", REC_LANGS],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            err_log = sub_output_dir / "ocr_errors.log"
            err_log.write_text(proc.stderr, encoding="utf-8")
            print(f"❌ OCR 处理失败: {sub}")
            print(proc.stderr)
        elif proc.stderr.strip():
            err_log = sub_output_dir / "ocr_errors.log"
            err_log.write_text(proc.stderr, encoding="utf-8")
            if args.verbose:
                print(f"⚠️ OCR 处理完成但有警告: {sub}")
                print(proc.stderr)
        else:
            if args.verbose:
                print(f"✅ OCR 处理成功: {sub}")
            if (sub_output_dir / "ocr_errors.log").exists():
                (sub_output_dir / "ocr_errors.log").unlink()
        print("----------------------------------------")

    duration = int(time.time() - start)
    print(f"\n✅ OCR 处理完成! 耗时: {duration // 60} 分 {duration % 60} 秒")
    print(f"处理了 {total_dirs} 个子目录")
    print(f"📁 OCR 结果保存在: {output_dir}")


if __name__ == "__main__":
    main()
