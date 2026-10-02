"""table_diff 回归测试。

重点覆盖 2026-10 修复的两个缺陷（都会让「双读校验」静默失效）：

1. `compare()` 只在差异数达到 `max_show`(默认 12) 时才返回差异，少量差异
   被吞掉 → 谎报「完全一致」。案例：11 处真实差异仍报 ✅。
2. 表头行比数据行短时，`rows_a[0][j]` 越界 → IndexError 崩溃。案例：
   表头 2 列、数据 3 列。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import table_diff  # noqa: E402


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def table(cells, header=("时间", "值")):
    """用给定数据行拼一张 Markdown 表。"""
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join("---" for _ in header) + " |"]
    for row in cells:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------- normalize

@pytest.mark.parametrize("raw, expected", [
    ("  12.5%  ", "12.5%"),
    ("−3.2", "-3.2"),          # U+2212 减号
    ("－3.2", "-3.2"),          # 全角减号
    ("－", ""),                 # 纯破折号 = 空单元格
    ("—", ""),
    ("50％", "50%"),            # 全角百分号
    ("1 000", "1000"),          # 内部空白
])
def test_normalize(raw, expected):
    assert table_diff.normalize(raw) == expected


# ------------------------------------------------------------ 核心回归：少差异

def test_single_cell_difference_is_reported():
    """★ 回归：1 处差异曾经被吞掉、谎报「完全一致」。"""
    a = [["时间", "值"], ["2006/12/29", "121.02%"]]
    b = [["时间", "值"], ["2006/12/29", "999.99"]]
    diffs = table_diff.compare(a, b, "A", "B")
    assert not diffs[0].startswith("__OK__"), "1 处差异必须报错"
    assert len(diffs) == 1
    assert "999.99" in diffs[0] and "121.02%" in diffs[0]


@pytest.mark.parametrize("n_diff", [1, 2, 5, 11])
def test_diffs_below_max_show_are_all_reported(n_diff):
    """★ 回归：差异数 < max_show 时，每一处都必须报出来。"""
    header = ["h"] + [f"c{i}" for i in range(20)]
    a = [list(header)]
    b = [list(header)]          # 必须各自复制，否则 a/b 共享同一行列表
    for k in range(n_diff):
        b[0][1 + k] = f"X{k}"
    diffs = table_diff.compare(a, b, "A", "B")
    assert len(diffs) == n_diff, f"{n_diff} 处差异应全部报出，实际 {len(diffs)}"
    assert not any(d.startswith("__OK__") for d in diffs)


def test_identical_tables_still_report_ok():
    a = [["时间", "值"], ["2006/12/29", "121.02%"]]
    b = [["时间", "值"], ["2006/12/29", "121.02%"]]
    diffs = table_diff.compare(a, b, "A", "B")
    assert len(diffs) == 1 and diffs[0].startswith("__OK__")
    assert "共比对 4 格" in diffs[0]


def test_normalized_equivalents_are_not_differences():
    """减号/全角百分号差异不算差异（normalize 已统一）。"""
    a = [["时间", "值"], ["x", "−3.2%"]]
    b = [["时间", "值"], ["x", "-3.2％"]]
    assert table_diff.compare(a, b, "A", "B")[0].startswith("__OK__")


# ------------------------------------------------- 核心回归：表头越界崩溃

def test_header_shorter_than_data_row_does_not_crash():
    """★ 回归：表头 2 列、数据 3 列时 rows_a[0][j] 越界崩溃。"""
    a = [["a", "b"], ["1", "2", "3"]]
    b = [["a", "b"], ["1", "2", "9"]]
    diffs = table_diff.compare(a, b, "A", "B")   # 不应抛异常
    assert len(diffs) == 1
    assert "第3列" in diffs[0]


def test_empty_header_row_does_not_crash():
    a = [[], ["1", "2"]]
    b = [[], ["1", "9"]]
    diffs = table_diff.compare(a, b, "A", "B")
    assert any("9" in d for d in diffs)


# ------------------------------------------------------------ 行列数不一致

def test_row_count_mismatch_is_reported():
    a = [["h"], ["1"], ["2"]]
    b = [["h"], ["1"]]
    diffs = table_diff.compare(a, b, "A", "B")
    assert any("行数不同" in d for d in diffs)


def test_column_count_mismatch_is_reported():
    a = [["h1", "h2"], ["1", "2"]]
    b = [["h1", "h2"], ["1", "2", "3"]]
    diffs = table_diff.compare(a, b, "A", "B")
    assert any("列数不同" in d for d in diffs)


# ------------------------------------------------------------ max_show 截断

def test_max_show_truncates_but_marks_truncation():
    header = ["h"] + [f"c{i}" for i in range(30)]
    a = [header]
    b = [header[:]]
    for k in range(30):
        b[0][1 + k] = f"X{k}"
    diffs = table_diff.compare(a, b, "A", "B", max_show=12)
    assert any("差异过多" in d for d in diffs)
    assert sum(1 for d in diffs if "第 1 行" in d) == 12
    assert not any(d.startswith("__OK__") for d in diffs)


# ------------------------------------------------------------------ parse

def test_parse_table_skips_separator_and_non_table_lines():
    text = ("# 标题\n\n"
            "| 时间 | 值 |\n"
            "| --- | --- |\n"
            "| 2006/12/29 | 121.02% |\n"
            "\n> 注：随便写点\n")
    p = Path("/tmp/_td_parse_probe.md")
    p.write_text(text, encoding="utf-8")
    rows = table_diff.parse_table(p)
    assert rows == [["时间", "值"], ["2006/12/29", "121.02%"]]
    p.unlink()


def test_parse_table_strips_outer_pipes_only():
    p = Path("/tmp/_td_parse_probe2.md")
    p.write_text("| a | b |\n| --- | --- |\n| 1 | 2 |\n", encoding="utf-8")
    assert table_diff.parse_table(p) == [["a", "b"], ["1", "2"]]
    p.unlink()


# -------------------------------------------------------------------- main

def test_main_exit_codes(tmp_path):
    same = write(tmp_path, "same.md", table([["1", "2"]]))
    other = write(tmp_path, "other.md", table([["1", "3"]]))

    assert table_diff.main([str(same), str(same)]) == 0      # 一致 → 0
    assert table_diff.main([str(same), str(other)]) == 1     # 有差异 → 1


def test_main_reports_one_cell_difference(tmp_path, capsys):
    """端到端：CLI 层也不能吞掉单格差异。"""
    a = write(tmp_path, "a.md", table([["1", "2"], ["3", "4"]]))
    b = write(tmp_path, "b.md", table([["1", "2"], ["3", "99"]]))
    rc = table_diff.main([str(a), str(b)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "❌" in out and "99" in out


def test_main_rejects_empty_side(tmp_path):
    empty = write(tmp_path, "empty.md", "没有表格\n")
    good = write(tmp_path, "good.md", table([["1", "2"]]))
    assert table_diff.main([str(empty), str(good)]) == 1
