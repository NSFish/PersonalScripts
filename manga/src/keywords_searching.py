#!/usr/bin/env python3
"""基于 OCR 结果(JSON)筛选包含关键词的图片。

替代原 keywords_searching.sh：用 json 标准库读取 OCR 文本，不再依赖 jq。
输出目录为 <原始图片父目录的父目录>/keyword_output。
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path


def load_texts(jf: Path):
    try:
        with open(jf, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return ""
    texts = data.get("texts") if isinstance(data, dict) else None
    if texts is None:
        return ""
    if isinstance(texts, str):
        return texts
    return json.dumps(texts, ensure_ascii=False)


def process_subdir(
    ocr_sub: Path,
    sub_name: str,
    parent_dir: Path,
    output_dir: Path,
    keywords,
    dry_run: bool,
    verbose: bool,
) -> None:
    sub_dir = parent_dir / sub_name
    if not ocr_sub.is_dir():
        if verbose:
            print(f"⚠️ 跳过: {sub_name} (无OCR结果)")
        return

    sub_output_dir = output_dir / sub_name
    sub_output_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(ocr_sub.glob("*.json"))
    if not json_files:
        if verbose:
            print(f"⚠️ 跳过: {sub_name} (无JSON文件)")
        return

    found_keyword = False
    match_count = 0
    for jf in json_files:
        img_name = jf.name[:-5]  # 去掉 .json
        img_path = sub_dir / img_name
        ocr_text = load_texts(jf)
        if not ocr_text or ocr_text == "null":
            continue

        if verbose:
            print(f"   处理文件: {img_name}")
            print(f"   OCR 结果: {ocr_text[:50]}...")

        if any(kw in ocr_text for kw in keywords):
            if img_path.is_file():
                if dry_run:
                    shutil.copy(img_path, sub_output_dir)
                    print(f"   预览: 复制 {img_path} 到 {sub_output_dir}")
                else:
                    shutil.move(img_path, sub_output_dir)
                    print(f"   匹配图片: {img_path} 已移动到 {sub_output_dir}")
                match_count += 1
                found_keyword = True
            elif verbose:
                print(f"   ⚠️ 图片不存在: {img_path}")

    if found_keyword and match_count > 0:
        new_sub_output_dir = output_dir / f"{sub_name}（{match_count}）"
        sub_output_dir.rename(new_sub_output_dir)
        print(f"✅ {sub_name} 中找到 {match_count} 张匹配图片")
    else:
        if verbose:
            print(f"⚠️ {sub_name} 中未找到匹配图片")
        if not dry_run and sub_output_dir.is_dir():
            shutil.rmtree(sub_output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="图片关键词匹配器")
    parser.add_argument("-n", "--dry-run", action="store_true", help="预览模式(不实际移动文件)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细处理信息")
    parser.add_argument("parent_dir", help="原始图片的父目录")
    parser.add_argument("ocr_dir", help="OCR 处理结果目录(直接包含 .json 文件)")
    parser.add_argument("keywords", nargs="+", help="一个或多个关键词")
    args = parser.parse_args()

    parent_dir = Path(args.parent_dir).resolve()
    ocr_dir = Path(args.ocr_dir).resolve()
    if not parent_dir.is_dir():
        print(f"错误: 原始图片目录不存在: {parent_dir}")
        sys.exit(1)
    if not ocr_dir.is_dir():
        print(f"错误: OCR目录不存在: {ocr_dir}")
        sys.exit(1)

    output_dir = parent_dir.parent / "keyword_output"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    print(f"📁 创建输出目录: {output_dir}")

    subdirs = sorted(p for p in ocr_dir.iterdir() if p.is_dir())
    total_dirs = len(subdirs)
    if total_dirs == 0:
        print(f"❌ OCR目录中找不到子目录: {ocr_dir}")
        sys.exit(1)
    print(f"✅ 找到 {total_dirs} 个OCR处理过的子目录")

    start = time.time()
    for processed, sub in enumerate(subdirs, 1):
        print(f"🔄 处理进度: {processed}/{total_dirs} - {sub.name}")
        process_subdir(sub, sub.name, parent_dir, output_dir, args.keywords, args.dry_run, args.verbose)
        print("----------------------------------------")

    duration = int(time.time() - start)
    out_dirs = sum(1 for p in output_dir.iterdir() if p.is_dir())
    total_matches = sum(1 for p in output_dir.rglob("*") if p.is_file())
    print(f"\n✅ 关键词匹配完成! 耗时: {duration // 60} 分 {duration % 60} 秒")
    print(f"处理了 {total_dirs} 个子目录")
    print(f"找到 {out_dirs} 个包含匹配图片的目录")
    print(f"共找到 {total_matches} 张匹配图片")
    print(f"📁 匹配结果保存在: {output_dir}")


if __name__ == "__main__":
    main()
