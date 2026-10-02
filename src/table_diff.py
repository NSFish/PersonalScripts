#!/usr/bin/env python3
"""逐格比对两份 Markdown 表格（用于「双读校验」）。

同一张表两个人/两次独立转录后，用这个命令找出所有不一致的格子；
一致才是可以直接用的转录，不一致的回原图定夺。

用法：
    table-diff a.md b.md

退出码：0 = 完全一致；1 = 有差异（差异明细打到 stdout）。
"""
import argparse
import re
import sys
from pathlib import Path

NORMALIZE = [
    (re.compile(r"[\s\u3000]"), ""),          # 空白
    (re.compile(r"[−－–—]"), "-"),            # 各种减号/破折号统一
    (re.compile(r"％"), "%"),
    (re.compile(r"^[-—]+$"), ""),             # 只有破折号＝空单元格
]


def normalize(cell):
    text = cell.strip()
    for pattern, repl in NORMALIZE:
        text = pattern.sub(repl, text)
    return text


def parse_table(path):
    """读出一个 Markdown 表格 → [[cell, ...], ...]（去掉分隔行）。"""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells if c.strip()):
            continue                          # | --- | 分隔行
        rows.append([c.strip() for c in cells])
    return rows


def compare(rows_a, rows_b, name_a, name_b, max_show=12):
    """逐格比对，返回差异描述列表；无差异时返回单条 `__OK__ …`。

    注意：**任何**差异都必须返回，不能只在差异数达到 max_show 时才返回——
    否则少量差异会被吞掉、谎报「完全一致」（2026-10 修复）。
    """
    diffs = []
    if len(rows_a) != len(rows_b):
        diffs.append(f"行数不同：{name_a} {len(rows_a)} 行，{name_b} {len(rows_b)} 行")
    ncmp = 0
    for i in range(min(len(rows_a), len(rows_b))):
        row_a, row_b = rows_a[i], rows_b[i]
        if len(row_a) != len(row_b):
            diffs.append(f"第 {i + 1} 行列数不同：{len(row_a)} vs {len(row_b)}"
                         f"（{' | '.join(row_a[:6])}）")
            continue
        for j in range(len(row_a)):
            ncmp += 1
            a, b = normalize(row_a[j]), normalize(row_b[j])
            if a != b:
                label = row_a[0] or f"第{i + 1}行"
                # 表头行可能比数据行短（表头/数据列数不一致的表），越界时回落到列号
                header = rows_a[0][j] if rows_a and j < len(rows_a[0]) else f"第{j + 1}列"
                diffs.append(f"第 {i + 1} 行（{label}）第 {j + 1} 列（{header}）："
                             f"{name_a}={row_a[j]!r}  {name_b}={row_b[j]!r}")
                if len(diffs) >= max_show:
                    diffs.append(f"…（差异过多，只显示前 {max_show} 处；"
                                 f"共比对 {ncmp}+ 格）")
                    return diffs
    if diffs:
        return diffs
    return [f"__OK__ 共比对 {ncmp} 格"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="逐格比对两份 Markdown 表格")
    parser.add_argument("a", help="转录 A 的 md 文件")
    parser.add_argument("b", help="转录 B 的 md 文件")
    parser.add_argument("--label-a", default="A")
    parser.add_argument("--label-b", default="B")
    parser.add_argument("--skip-a", type=int, default=0,
                        help="A 开头跳过几行（两侧表头表示不同时用，例如多级表头）")
    parser.add_argument("--skip-b", type=int, default=0, help="B 开头跳过几行")
    args = parser.parse_args(argv)

    rows_a, rows_b = parse_table(args.a), parse_table(args.b)
    rows_a, rows_b = rows_a[args.skip_a:], rows_b[args.skip_b:]
    if not rows_a or not rows_b:
        print("❌ 有一侧没解析到表格内容（或跳过过多行）", file=sys.stderr)
        return 1
    diffs = compare(rows_a, rows_b, args.label_a, args.label_b)
    shape = f"{len(rows_a)} 行 × {len(rows_a[0])} 列"
    ok_prefix = "__OK__"
    detail = diffs[0][len(ok_prefix) + 1:] if diffs and diffs[0].startswith(ok_prefix) else ""
    if diffs and diffs[0].startswith(ok_prefix):
        print(f"✅ {Path(args.a).name}：双读完全一致（{shape}，{detail}）")
        return 0
    if not diffs:
        print(f"✅ {Path(args.a).name}：双读完全一致（{shape}）")
        return 0
    print(f"❌ {Path(args.a).name}：{len(diffs)} 处不一致（{shape}）")
    for d in diffs:
        print(f"   - {d}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
