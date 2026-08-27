#!/usr/bin/env python3
"""把子文件夹名里的中文/阿拉伯数字序号规范化。

合并原 convert_cn_numbers_to_arab（--style prefix）与
convert_chinese_numbers_to_arab（--style replace）：

- prefix : "第X话/条" -> "<序号> <原名>"（按序号排序后零填充前缀）
- replace: "第X话/章" -> "<序号> 余文"；"第X条" -> "第 <序号> 条 余文"
"""
import argparse
import re
import sys
from pathlib import Path

from _common import cn_to_arab, pad

STRIP = " \t" + "".join(chr(c) for c in range(33, 48))  # 常见 ASCII 标点


def _rename_replace(name: str):
    """第X条 -> '第 <序号> 条 余文'；第X话/章 -> '<序号> 余文'。返回新名或 None/'FAIL'。"""
    m = re.match(r"^第([^条]+)条(.*)$", name)
    if m:
        arabic = cn_to_arab(m.group(1))
        if arabic is None:
            return "FAIL"
        rest = (m.group(2) or "").lstrip(STRIP)
        return f"第 {arabic} 条" + (f" {rest}" if rest else "")
    m = re.match(r"^第?([^话章]+)[话章](.*)$", name)
    if m:
        arabic = cn_to_arab(m.group(1))
        if arabic is None:
            return "FAIL"
        rest = (m.group(2) or "").lstrip(STRIP)
        return f"{arabic}" + (f" {rest}" if rest else "")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="中文/阿拉伯数字文件夹名规范化")
    parser.add_argument(
        "--style", choices=["prefix", "replace"], default="prefix",
        help="prefix: 加序号前缀(默认); replace: 原地替换数字",
    )
    parser.add_argument("-n", "--dry-run", action="store_true", help="预览模式(不重命名)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细处理信息")
    parser.add_argument("folder_path", help="文件夹路径")
    args = parser.parse_args()

    folder = Path(args.folder_path).resolve()
    if not folder.is_dir():
        print(f"错误：必须指定文件夹路径: {folder}")
        sys.exit(1)

    mode = "预览模式" if args.dry_run else "执行模式"
    print(f"开始处理文件夹: {folder}  (style={args.style})")
    print(f"操作模式: {mode}")
    print()

    results = []  # prefix: (sub, name, arabic) ; replace: (sub, name, new_name)
    for sub in sorted(d for d in folder.iterdir() if d.is_dir()):
        name = sub.name
        if args.style == "prefix":
            m = re.match(r"^第(.+?)[话条](.*)$", name)
            if not m:
                if args.verbose:
                    print(f"{name} -> 无须处理")
                continue
            arabic = cn_to_arab(m.group(1))
            if arabic is None:
                print(f"{name} -> 转换失败 (无法识别的数字格式: {m.group(1)})")
                continue
            results.append((sub, name, arabic))
        else:
            new = _rename_replace(name)
            if new is None:
                if args.verbose:
                    print(f"{name} -> 无须处理")
                continue
            if new == "FAIL":
                print(f"{name} -> 转换失败")
                continue
            results.append((sub, name, new))

    if args.style == "prefix":
        results.sort(key=lambda r: r[2])
        width = len(str(len(results)))

    for idx, item in enumerate(results):
        sub, name, payload = item
        if args.style == "prefix":
            new_name = f"{pad(idx, width)} {name}"
        else:
            new_name = payload
        print(f"{name} -> {new_name}")
        if not args.dry_run:
            sub.rename(sub.with_name(new_name))

    print(f"\n处理完成! 共处理 {len(results)} 个子文件夹")


if __name__ == "__main__":
    main()
