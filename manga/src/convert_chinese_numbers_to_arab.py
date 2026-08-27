#!/usr/bin/env python3
"""把子文件夹名里的中文数字序号转成阿拉伯数字。

替代原 convert_chinese_numbers_to_arab.sh：
- 第X话/集/章/回/节 -> "阿拉伯数字 余下文本"
- 第X条 -> "第 阿拉伯数字 条 余下文本"
"""
import argparse
import cn2an
import re
import sys
from pathlib import Path

STRIP = " \t" + "".join(chr(c) for c in range(33, 48))  # 常见 ASCII 标点


def convert(cn: str):
    if cn.isdigit():
        return int(cn)
    try:
        return cn2an.cn2an(cn, "normal")
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="中文数字文件夹名转阿拉伯数字")
    parser.add_argument("-n", "--dry-run", action="store_true", help="预览模式(不重命名)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细处理信息")
    parser.add_argument("folder_path", help="文件夹路径")
    args = parser.parse_args()

    folder = Path(args.folder_path).resolve()
    if not folder.is_dir():
        print(f"错误：必须指定文件夹路径: {folder}")
        sys.exit(1)

    mode = "预览模式" if args.dry_run else "执行模式"
    print(f"开始处理文件夹: {folder}")
    print(f"操作模式: {mode}")
    print()

    for sub in sorted(d for d in folder.iterdir() if d.is_dir()):
        name = sub.name

        m = re.match(r"^第([^条]+)条(.*)$", name)
        if m:
            arabic = convert(m.group(1))
            if arabic is None:
                print(f"{name} -> 转换失败 (无法识别的数字格式: {m.group(1)})")
                continue
            rest = (m.group(2) or "").lstrip(STRIP)
            new_name = f"第 {arabic} 条" + (f" {rest}" if rest else "")
            print(f"{name} -> {new_name}")
            if not args.dry_run:
                sub.rename(sub.with_name(new_name))
            continue

        m = re.match(r"^第?([^话章]+)[话章](.*)$", name)
        if m:
            arabic = convert(m.group(1))
            if arabic is None:
                print(f"{name} -> 转换失败 (无法识别的数字格式: {m.group(1)})")
                continue
            rest = (m.group(2) or "").lstrip(STRIP)
            new_name = f"{arabic}" + (f" {rest}" if rest else "")
            print(f"{name} -> {new_name}")
            if not args.dry_run:
                sub.rename(sub.with_name(new_name))
            continue

        if re.match(r"^[0-9]+", name):
            print(f"{name} -> 无须处理 (已经是数字格式)")
        else:
            print(f"{name} -> 无须处理 (不符合转换格式)")


if __name__ == "__main__":
    main()
