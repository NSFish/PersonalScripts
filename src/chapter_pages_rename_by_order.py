#!/usr/bin/env python3
"""递归把每个子目录（含目标目录自身）里的文件按排序重命名为零填充序号。

替代原 chapter_pages_rename_by_order.sh：纯 pathlib 逻辑，跨平台。
支持 -n/--dry-run 预览、-v/--verbose。
"""
import argparse
import sys
import uuid
from pathlib import Path

from _common import natural_key, pad

TMP_PREFIX = "__rename_tmp_"


def plan_names(files: list[Path]) -> list[tuple[Path, str]]:
    """给排序后的文件列表规划零填充序号新名，返回 [(原路径, 新名)]。

    序号从 0 起始，位宽 max(2, len(str(总数)))，保留原扩展名；
    已经是规范名的文件不进 plan（保持幂等、汇总数字真实）。
    被 ebook_2_zip 等脚本复用：命名规则只有这一处定义。
    """
    n = len(files)
    if n == 0:
        return []
    digit = max(2, len(str(n)))
    plan = []
    for i, f in enumerate(files):
        new_name = f"{pad(i, digit)}{f.suffix}"
        if new_name != f.name:
            plan.append((f, new_name))
    return plan


def process_directory(d: Path, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """处理单个目录，返回 (成功重命名数, 失败数)。"""
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
        return 0, 0

    plan = plan_names(files)

    if not plan:
        if verbose:
            print("  文件名已规范，无需处理")
        return 0, 0

    if dry_run:
        for f, new_name in plan:
            print(f'  ✅  "{f.name}" -> "{new_name}"')
        return len(plan), 0

    # 两步重命名：先搬到唯一临时名，再搬到目标名，避免序号交叉覆盖。
    token = uuid.uuid4().hex[:8]
    tmps = []
    failed = 0
    for i, (f, new_name) in enumerate(plan):
        tmp = f.with_name(f"{TMP_PREFIX}{token}_{i}__{f.suffix}")
        while tmp.exists():  # 极端情况下撞名，换一个 token
            token = uuid.uuid4().hex[:8]
            tmp = f.with_name(f"{TMP_PREFIX}{token}_{i}__{f.suffix}")
        try:
            f.rename(tmp)
        except OSError as e:
            print(f'❌  "{f.name}" 重命名失败: {e}')
            failed += 1
            continue
        tmps.append((f.name, tmp, new_name))

    renamed = 0
    for orig_name, tmp, new_name in tmps:
        try:
            tmp.rename(tmp.with_name(new_name))
        except OSError as e:
            print(f'❌  "{orig_name}" -> "{new_name}" 失败: {e}')
            failed += 1
            continue
        print(f'✅  "{orig_name}" -> "{new_name}"')
        renamed += 1

    leftovers = sorted(p.name for p in d.iterdir() if p.name.startswith(TMP_PREFIX))
    if leftovers:
        print(f"⚠️  目录仍有残留临时文件: {d} -> {leftovers}")

    return renamed, failed


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
    if args.verbose:
        print(f"🔍 扫描目录: {target}")

    # 目标目录自身也要处理（旧 shell 版语义），再递归子目录。
    dirs = [target]
    dirs.extend(sorted(p for p in target.rglob("*") if p.is_dir()))

    dirs_done = 0
    renamed = 0
    failed = 0
    for d in dirs:
        got, bad = process_directory(d, args.dry_run, args.verbose)
        failed += bad
        if got:
            dirs_done += 1
            renamed += got

    if args.dry_run:
        print(f"\n共扫描 {len(dirs)} 个文件夹，待重命名 {renamed} 个文件")
    else:
        print(f"\n共处理 {dirs_done} 个文件夹，重命名 {renamed} 个文件")
    if failed:
        print(f"❌ {failed} 个文件处理失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
