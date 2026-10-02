#!/usr/bin/env python3
"""递归对子目录中的图片做 OCR，结果存为 JSON。

用 pyobjc 直接调用 macOS 的 Vision 框架（VNRecognizeTextRequest），
不再依赖仓库根的 macos-vision-ocr-arm64 二进制。
输出到 <父目录的父目录>/<输入目录名>_ocr_result/，每个图片一个
<图片名>.json，内容为 {"texts": "<识别文本，按行\\n连接>"}，
供 keywords_searching.py 消费。
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import Vision
import Quartz
from Foundation import NSURL

from _common import is_image_file


REC_LANGS = ["zh-Hans", "zh-Hant", "en-US"]


def cg_image_from_path(path: Path):
    url = NSURL.fileURLWithPath_(str(path))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        return None
    return Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)


def ocr_image(cg_image):
    """识别图片文字，按行拼接；OCR 请求失败返回 None（区别于识别结果为空）。"""
    request = Vision.VNRecognizeTextRequest.new()
    request.setRecognitionLanguages_(REC_LANGS)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    ok, error = handler.performRequests_error_([request], None)
    if not ok or error:
        return None
    lines = []
    for obs in request.results() or []:
        txt = obs.text()
        if txt:
            lines.append(txt)
    return "\n".join(lines)


def ocr_subdir(sub: Path, out_sub: Path, verbose: bool) -> str:
    out_sub.mkdir(parents=True, exist_ok=True)
    errors = []
    for img in sorted(p for p in sub.iterdir() if p.is_file() and is_image_file(p)):
        cg = cg_image_from_path(img)
        if cg is None:
            errors.append(f"无法读取图片: {img.name}")
            continue
        text = ocr_image(cg)
        if text is None:
            errors.append(f"OCR 请求失败: {img.name}")
            continue
        (out_sub / f"{img.name}.json").write_text(
            json.dumps({"texts": text}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if verbose:
            print(f"   ✅ {img.name}: {text[:40]!r}")
    return "\n".join(errors)


def main() -> None:
    parser = argparse.ArgumentParser(description="图片 OCR 处理器 (Apple Vision)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细处理信息")
    parser.add_argument("parent_dir", help="父文件夹路径")
    args = parser.parse_args()

    parent_dir = Path(args.parent_dir).resolve()
    if not parent_dir.is_dir():
        print(f"错误: 文件夹不存在: {parent_dir}")
        sys.exit(1)

    output_base = parent_dir.parent
    output_dir = output_base / f"{parent_dir.name}_ocr_result"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    subdirs = sorted(p for p in parent_dir.iterdir() if p.is_dir())
    if not subdirs:
        print(f"❌ 在 {parent_dir} 中找不到子目录")
        sys.exit(1)

    print(f"📁 创建输出目录: {output_dir}")
    print(f"✅ 找到 {len(subdirs)} 个子目录")

    start = time.time()
    for processed, sub in enumerate(subdirs, 1):
        print(f"🔄 处理进度: {processed}/{len(subdirs)} - {sub.name}")
        errs = ocr_subdir(sub, output_dir / sub.name, args.verbose)
        if errs:
            (output_dir / sub.name / "ocr_errors.log").write_text(errs, encoding="utf-8")
            print(f"⚠️ {sub.name} 处理完成但有错误")
        elif args.verbose:
            print(f"✅ {sub.name} 处理成功")
        print("----------------------------------------")

    duration = int(time.time() - start)
    print(f"\n✅ OCR 处理完成! 耗时: {duration // 60} 分 {duration % 60} 秒")
    print(f"处理了 {len(subdirs)} 个子目录")
    print(f"📁 OCR 结果保存在: {output_dir}")


if __name__ == "__main__":
    main()
