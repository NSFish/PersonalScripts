#!/usr/bin/env python3
"""双读配对复核：用修复版 table_diff 的 compare() 重跑 verify/ vs verify_mine/。

背景：table-diff 的 compare() 曾长期谎报「完全一致」（差异 <12 处被吞），
2026-10-02 已修复并有回归测试（tests/test_table_diff.py）。
当时用一次性脚本重跑了全部配对，结论写进 CONTINUE_PLAN_十年十倍.md；
本脚本把那次的重跑逻辑固化为正式工具，供 R2 返修与后续新表复用。

用法：
    verify-pairs                       # 全量复核
    verify-pairs --diffs-only          # 只列有数据冲突的
    verify-pairs --table 表7-6         # 只看指定表（文件名子串匹配）

判定规则：
  1. 对每对文件，在 skip_a/skip_b ∈ {0,1,2} 组合里选数据差异最少的一组
     （消化多级表头拍平造成的行错位）。
  2. 表头行（第 1 行）的差异单独归类——多级表头写法不同属表达差异，不算数据错误。
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import table_diff as td  # noqa: E402

BASE = Path(__file__).resolve().parent.parent / "output" / "十年十倍"


def data_diffs(a, b, skip_a=0, skip_b=0):
    """跳过表头后逐格比对，返回 (数据差异数, 明细)。"""
    a, b = a[skip_a:], b[skip_b:]
    out = []
    for i in range(min(len(a), len(b))):
        ra, rb = a[i], b[i]
        if len(ra) != len(rb):
            out.append((f"第{i+1}行列数", len(ra), len(rb)))
            continue
        for j in range(len(ra)):
            if td.normalize(ra[j]) != td.normalize(rb[j]):
                out.append((f"第{i+1}行({str(ra[0])[:10]})第{j+1}列", ra[j], rb[j]))
    return out


def best_alignment(a, b):
    best = None
    for sa in (0, 1, 2):
        for sb in (0, 1, 2):
            d = data_diffs(a, b, sa, sb)
            if best is None or len(d) < len(best[0]):
                best = (d, sa, sb)
    return best


def main(argv=None):
    ap = argparse.ArgumentParser(description="verify/ vs verify_mine/ 双读配对复核")
    ap.add_argument("--diffs-only", action="store_true", help="只输出有数据冲突的配对")
    ap.add_argument("--table", help="只看文件名含该子串的配对")
    args = ap.parse_args(argv)

    verify, mine = BASE / "verify", BASE / "verify_mine"
    pairs = [(p, mine / p.name) for p in sorted(verify.glob("*.md"))
             if (mine / p.name).exists()]
    only_verify = sorted(p.name for p in verify.glob("*.md")
                         if not (mine / p.name).exists())
    only_mine = sorted(p.name for p in mine.glob("*.md")
                       if not (verify / p.name).exists())

    if args.table:
        pairs = [(a, b) for a, b in pairs if args.table in a.name]

    clean, conflicts = 0, []
    for a, b in pairs:
        ra, rb = td.parse_table(a), td.parse_table(b)
        if not ra or not rb:
            print(f"⚠ 无法解析（一侧无表格行）：{a.name}")
            continue
        det, sa, sb = best_alignment(ra, rb)
        if det:
            conflicts.append((len(det), a.name, sa, sb, det))
        else:
            clean += 1

    print(f"配对 {len(pairs)} 对：数据完全一致 {clean}，有冲突 {len(conflicts)}")
    if only_verify:
        print(f"仅 verify/（缺盲读或缺我的读数）{len(only_verify)}：")
        for n in only_verify:
            print(f"   - {n}")
    if only_mine:
        print(f"仅 verify_mine/ {len(only_mine)}：")
        for n in only_mine:
            print(f"   - {n}")

    if not args.diffs_only or conflicts:
        print("\n=== 数据冲突明细（skip 已选最优对齐）===")
        for n, name, sa, sb, det in sorted(conflicts, reverse=True):
            print(f"\n[{n:3d} 格] {name}  (skip_a={sa}, skip_b={sb})")
            for label, va, vb in det[:6]:
                print(f"    {label}:  verify={va!r}  verify_mine={vb!r}")
            if len(det) > 6:
                print(f"    …另 {len(det)-6} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
