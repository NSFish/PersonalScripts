"""_common 公共函数的单元测试。"""
from pathlib import Path

from _common import cn_to_arab, is_image_file, natural_key, pad


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
