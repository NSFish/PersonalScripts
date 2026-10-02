#!/usr/bin/env python3
"""规范化目标目录中的文件/文件夹名称并生成 source.txt 排序列表。

替代原 generate_source_file.sh：
- 提取序号：纯数字前缀 / 第X话集章回节 / Episode X
- 格式化序号：按文件总数自动确定位数
- 数字与汉字间自动加空格（CJK 码点 0x4E00-0x9FFF）
"""
import argparse
import re
import string
import sys
from pathlib import Path

from _common import natural_key, pad, cn_to_arab


def is_han(ch: str) -> bool:
    c = ord(ch)
    return 0x4E00 <= c <= 0x9FFF


def sort_key(s: str):
    m = re.match(r"(\d+)", s)
    return (int(m.group(1)), s) if m else (10**18, s)


def extract_number(name: str):
    """返回 (num:int, rest:str)，无法提取返回 None。"""
    # 第X话/集/章/回/节（X 可为阿拉伯数字或中文数字）
    m = re.match(r"^第(.+?)[话集章回节](.*)$", name)
    if m:
        cn = m.group(1)
        rest = m.group(2) or ""
        num = cn_to_arab(cn)
        if num is None:
            return None
        return num, rest
    # Episode X
    m = re.match(r"^[Ee]pisode\s*0*(\d+)(.*)$", name)
    if m:
        return int(m.group(1)), m.group(2) or ""
    # 纯数字前缀
    m = re.match(r"^0*(\d+)(.*)$", name)
    if m:
        return int(m.group(1)), m.group(2) or ""
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="规范化文件名并生成 source.txt")
    parser.add_argument("target_dir", help="目标目录")
    args = parser.parse_args()

    target = Path(args.target_dir).resolve()
    if not target.is_dir():
        print(f"Usage: {sys.argv[0]} <directory>", file=sys.stderr)
        sys.exit(1)

    files = sorted(
        (
            f for f in target.iterdir()
            if f.is_file() and not f.name.startswith(".") and f.name != "source.txt"
        ),
        key=lambda f: natural_key(f.name),
    )
    total = len(files)
    width = len(str(total))

    error_log = []
    rename_map = []
    renamed_files = []

    for file in files:
        name = file.name
        extracted = extract_number(name)
        if extracted is None:
            error_log.append(f"无法提取序号: '{name}'")
            renamed_files.append(name)
            continue

        num, rest = extracted
        num_padded = pad(num, width)
        rest = rest.lstrip(string.punctuation + " \t").rstrip(" \t")

        # 数字与汉字之间加空格
        processed = ""
        prev = ""
        for ch in rest:
            if is_han(ch) and prev.isdigit():
                processed += " " + ch
            elif ch.isdigit() and is_han(prev):
                processed += " " + ch
            else:
                processed += ch
            prev = ch
        processed = re.sub(r" +", " ", processed).strip()

        new_name = f"{num_padded} {processed}" if processed else f"{num_padded}"

        if name != new_name:
            dest = target / new_name
            if dest.exists():
                # os.rename 会静默覆盖已有文件，冲突时跳过并报错
                error_log.append(f"目标已存在，跳过重命名: '{name}' -> '{new_name}'")
                renamed_files.append(name)
                continue
            try:
                file.rename(dest)
                rename_map.append(f"{name} -> {new_name}")
                renamed_files.append(new_name)
            except OSError as e:
                error_log.append(f"重命名失败: '{name}' -> '{new_name}' ({e})")
                renamed_files.append(name)
        else:
            renamed_files.append(name)

    renamed_files.sort(key=sort_key)
    (target / "source.txt").write_text("\n".join(renamed_files) + "\n", encoding="utf-8")
    print("已生成 source.txt 文件")

    if rename_map:
        print("\n📁 重命名映射关系：")
        for r in rename_map:
            print(f"  {r}")

    if error_log:
        print("\n❌ 发现以下错误：", file=sys.stderr)
        for e in error_log:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(10)

    print("\n操作完成！")


if __name__ == "__main__":
    main()
