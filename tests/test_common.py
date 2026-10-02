"""_common 公共函数的单元测试。"""
from pathlib import Path

import pytest

from _common import (
    cn_to_arab,
    is_hidden_part,
    is_image_file,
    iter_files,
    list_archives,
    list_images,
    natural_key,
    pad,
    prepare_result_dir,
)


def test_is_image_file():
    assert is_image_file("a.jpg")
    assert is_image_file("a.JPEG")
    assert is_image_file(Path("b.png"))
    assert is_image_file("c.webp")
    assert is_image_file("d.avif")
    assert not is_image_file("a.txt")
    assert not is_image_file("a")
    assert not is_image_file("a.jpg.tar")


def test_natural_key():
    items = ["f10", "f2", "f1"]
    assert sorted(items, key=natural_key) == ["f1", "f2", "f10"]
    assert natural_key("x1y") == ["x", 1, "y"]


def test_natural_key_superscript_digit():
    # 上标字符不是十进制位（re 的 \d 不匹配），作为普通文本段参与排序，不应崩溃
    assert natural_key("第²话") == ["第²话"]
    assert natural_key("a2²b") == ["a", 2, "²b"]


def test_pad():
    assert pad(3, 2) == "03"
    assert pad(12, 2) == "12"
    assert pad(0, 3) == "000"


def test_cn_to_arab():
    assert cn_to_arab("三") == 3
    assert cn_to_arab("十二") == 12
    assert cn_to_arab("一百零八") == 108
    assert cn_to_arab("23") == 23
    assert cn_to_arab("xyz") is None
    assert cn_to_arab("") is None


def test_mac_tags_round_trip(tmp_path):
    pytest.importorskip("Foundation")  # macOS 专属
    from _common import get_mac_tags, set_mac_tags

    f = tmp_path / "a.zip"
    f.write_bytes(b"x")
    assert get_mac_tags(f) == []
    assert set_mac_tags(f, ["Red"]) is True
    assert get_mac_tags(f) == ["Red"]
    assert set_mac_tags(f, []) is True   # 空列表应清除标签
    assert get_mac_tags(f) == []


def test_is_hidden_part():
    assert is_hidden_part(".DS_Store")
    assert is_hidden_part("__MACOSX")
    assert is_hidden_part(".git")          # 任意隐藏文件
    assert not is_hidden_part("a.jpg")
    assert not is_hidden_part("第1话")


def test_iter_files_excludes_hidden_and_sorts(tmp_path: Path):
    (tmp_path / "b").mkdir()
    (tmp_path / "__MACOSX").mkdir()
    for rel in ["10.jpg", "2.jpg", ".hidden", "b/1.jpg", "__MACOSX/._x"]:
        (tmp_path / rel).write_text("x")

    names = [str(p.relative_to(tmp_path)) for p in iter_files(tmp_path)]
    # 按相对路径自然排序：数字段按数值比，所以 2.jpg < 10.jpg；顶层文件排在 b/ 里的前面
    assert names == ["2.jpg", "10.jpg", "b/1.jpg"]


def test_list_images_and_archives(tmp_path: Path):
    (tmp_path / "p2.jpg").write_text("x")
    (tmp_path / "p10.jpg").write_text("x")
    (tmp_path / "b1.zip").write_text("x")
    (tmp_path / "b2.cbz").write_text("x")
    (tmp_path / "notes.txt").write_text("x")

    assert [p.name for p in list_images(tmp_path)] == ["p2.jpg", "p10.jpg"]
    assert [p.name for p in list_archives(tmp_path)] == ["b1.zip", "b2.cbz"]


def test_prepare_result_dir_creates_dir(tmp_path: Path):
    src = tmp_path / "book"
    src.mkdir()

    out = prepare_result_dir(src)

    assert out == tmp_path / "result"
    assert out.is_dir()


def test_prepare_result_dir_idempotent(tmp_path: Path):
    src = tmp_path / "book"
    src.mkdir()

    assert prepare_result_dir(src) == prepare_result_dir(src)  # 已存在也不报错
