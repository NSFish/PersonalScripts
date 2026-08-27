"""manga 脚本的功能回归测试：用临时目录真实运行各脚本，校验输出。

通过 subprocess 调用 venv 内的 python（即运行 pytest 的解释器）执行 manga/src 下的脚本，
脚本内 `from _common import ...` 因脚本目录在 sys.path[0] 而可用。
"""
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent.parent / "src"


def run(mod: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SRC / mod), *args],
        capture_output=True,
        text=True,
    )


def make_img(path: Path, w: int = 100, h: int = 100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (0, 0, 0)).save(path)


def test_double_page_crop_split_and_idempotency(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    make_img(d / "spread.png", 200, 80)   # 比例 2.5 -> 双页
    make_img(d / "single.png", 80, 200)   # 比例 0.4 -> 单页

    assert run("double_page_crop.py", str(d)).returncode == 0
    split = d.parent / "in_split"
    assert sorted(p.name for p in split.iterdir()) == [
        "single.png",
        "spread_01.png",
        "spread_02.png",
    ]

    # 再跑一次：已拆分的 _01/_02 不应被重复拆分
    assert run("double_page_crop.py", str(split)).returncode == 0
    assert sorted(p.name for p in split.iterdir()) == [
        "single.png",
        "spread_01.png",
        "spread_02.png",
    ]


def test_volume_split(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    for n in ["1.png", "2.png", "3.png", "4.png", "5.png"]:
        make_img(d / n, 10, 10)
    (tmp_path / "contents.txt").write_text("1 第一章 1\n2 第二章 3\n", encoding="utf-8")

    assert run("volume_split_into_chapters.py", str(d), "2.png", str(tmp_path / "contents.txt")).returncode == 0
    out = d.parent / "in_split"
    ch1 = out / "1 第一章"
    ch2 = out / "2 第二章"
    assert ch1.is_dir() and ch2.is_dir()
    assert len(list(ch1.iterdir())) == 2
    assert len(list(ch2.iterdir())) == 1


def test_cn_numbers_rename_prefix(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第3话 测试").mkdir(parents=True)
    (d / "第十二话 x").mkdir(parents=True)
    (d / "已经01 别的").mkdir(parents=True)

    assert run("cn_numbers_rename.py", "--style", "prefix", str(d)).returncode == 0
    assert sorted(p.name for p in d.iterdir()) == [
        "0 第3话 测试",
        "1 第十二话 x",
        "已经01 别的",
    ]


def test_cn_numbers_rename_replace(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第二话 测试").mkdir(parents=True)
    (d / "第三条 备注").mkdir(parents=True)
    (d / "第五章").mkdir(parents=True)

    assert run("cn_numbers_rename.py", "--style", "replace", str(d)).returncode == 0
    assert sorted(p.name for p in d.iterdir()) == [
        "2 测试",
        "5",
        "第 3 条 备注",
    ]


def test_generate_source_file(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "01话集.mp3").write_text("x")
    (d / "第3话 测试.txt").write_text("x")
    (d / "10话.txt").write_text("x")

    assert run("generate_source_file.py", str(d)).returncode == 0
    lines = (d / "source.txt").read_text(encoding="utf-8").splitlines()
    assert lines == ["1 话集.mp3", "3 测试.txt", "10 话.txt"]


def test_chapter_pages_rename_by_order(tmp_path: Path):
    sub = tmp_path / "top" / "sub"
    sub.mkdir(parents=True)
    for n in ["a.jpg", "b.jpg", "c.jpg"]:
        (sub / n).write_text("x")

    assert run("chapter_pages_rename_by_order.py", str(tmp_path / "top")).returncode == 0
    assert sorted(p.name for p in sub.iterdir()) == ["00.jpg", "01.jpg", "02.jpg"]


def test_insert_numbers(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第3话 xxx").mkdir(parents=True)
    (d / "第七条 yyy").mkdir(parents=True)

    assert run("insert_numbers_in_front_of_chapter_titles.py", str(d)).returncode == 0
    assert sorted(p.name for p in d.iterdir()) == [
        "0 第3话 xxx",
        "1 第七条 yyy",
    ]


def test_pages_organize(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    make_img(d / "abc_12_34.jpg")

    assert run("pages_organize_into_chapters.py", str(d)).returncode == 0
    assert (d / "12" / "abc_12_34.jpg").is_file()


def test_check_page_width(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    make_img(d / "a.png", 800, 100)
    make_img(d / "b.png", 800, 100)
    make_img(d / "c.png", 600, 100)

    r = run("check_page_width.py", str(d))
    assert r.returncode == 0
    assert "800" in r.stdout and "c.png" in r.stdout


def test_unzip_all(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    make_img(d / "img1.jpg", 10, 10)
    zip_path = d / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(d / "img1.jpg", "img1.jpg")
    (d / "img1.jpg").unlink()

    assert run("unzip_all.py", str(d)).returncode == 0
    assert (d / "book" / "img1.jpg").is_file()


def test_zip_all(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir(parents=True, exist_ok=True)
    sub = d / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    make_img(sub / "a.jpg", 10, 10)

    assert run("zip_all.py", str(d)).returncode == 0
    zp = d / "sub.zip"
    assert zp.is_file()
    with zipfile.ZipFile(zp) as zf:
        assert "sub/a.jpg" in zf.namelist()


def test_page_blender(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    make_img(a, 100, 100)
    make_img(b, 100, 100)

    assert run("page_blender.py", "-u", "50", str(a), str(b)).returncode == 0
    assert (tmp_path / "result_up_50.png").is_file()


def test_page_concat(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    make_img(a, 100, 100)
    make_img(b, 100, 100)

    assert run("page_concat.py", "-H", str(a), str(b)).returncode == 0
    assert list(tmp_path.glob("merged_*.jpg"))


def test_hentai_zip_rename_inside(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    zip_path = d / "mycomic.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("oldname/a.txt", "hello")

    assert run("hentai_zip_rename_inside.py", str(d)).returncode == 0
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.startswith("mycomic/") for n in names)


def test_keywords_searching(tmp_path: Path):
    parent = tmp_path / "imgs"
    sub = parent / "sub"
    sub.mkdir(parents=True)
    make_img(sub / "img1.jpg", 10, 10)

    ocr = tmp_path / "ocr"
    ocr_sub = ocr / "sub"
    ocr_sub.mkdir(parents=True)
    (ocr_sub / "img1.jpg.json").write_text(json.dumps({"texts": "hello keyword world"}), encoding="utf-8")

    assert run("keywords_searching.py", str(parent), str(ocr), "keyword").returncode == 0
    out = tmp_path / "keyword_output"
    assert out.is_dir()
    jpgs = list(out.rglob("*.jpg"))
    assert jpgs, "keyword_output 中应有匹配图片"
