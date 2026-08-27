#!/usr/bin/env python3
"""递归把每个子目录里的文件按排序重命名为零填充序号。

替代原 chapter_pages_rename_by_order.sh：纯 pathlib 逻辑，跨平台。
支持 -n/--dry-run 预览、-v/--verbose。
"""
import argparse
import sys
from pathlib import Path

from _common import natural_key, pad


def process_directory(d: Path, dry_run: bool, verbose: bool) -> None:
    if verbose:
        print(f"🛠 正在处理文件夹: {d}")

    files = sorted(
        (f for f in d.iterdir() if f.is_file() and not f.name.startswith(".")),
        key=lambda f: natural_key(f.name),
    )
    n = len(files)
    if n == 0:
        if verbose:
            print("  目录为空，跳过处理")
        return

    digit = max(2, len(str(n)))
    plan = []
    for i, f in enumerate(files):
        new_name = f"{pad(i, digit)}{f.suffix}"
        plan.append((f, new_name))

    if dry_run:
        for f, new_name in plan:
            print(f'  ✅  "{f.name}" -> "{new_name}"')
        return

    tmps = []
    for i, (f, new_name) in enumerate(plan):
        tmp = f.with_name(f"__rename_tmp_{i}__{f.suffix}")
        f.rename(tmp)
        tmps.append((tmp, new_name))

    for tmp, new_name in tmps:
        tmp.rename(tmp.with_name(new_name))
        print(f'✅  "{tmp.with_name(new_name).name}" -> "{new_name}"')


def main() -> None:
    parser = argparse.ArgumentParser(description="按数字排序重命名目录下的文件")
    parser.add_argument("-n", "--dry-run", action="store_true", help="预览模式(不实际重命名)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细处理过程")
    parser.add_argument("target_dir", help="目标目录")
    args = parser.parse_args()

    target = Path(args.target_dir).resolve()
    if not target.is_dir():
        print(f"错误：请指定正确的目标目录: {args.target_dir}")
        sys.exit(1)

    if args.dry_run:
        print("🏃 运行模式: 预览 (dry-run)")
    else:
        print("🏃 运行模式: 实际执行")

    for d in sorted(p for p in target.rglob("*") if p.is_dir() and p != target):
        process_directory(d, args.dry_run, args.verbose)


if __name__ == "__main__":
    main()
