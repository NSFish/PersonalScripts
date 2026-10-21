"""manga 脚本的功能回归测试：用临时目录真实运行各脚本，校验输出。

通过 subprocess 调用 venv 内的 python（即运行 pytest 的解释器）执行 src 下的脚本，
脚本内 `from _common import ...` 因脚本目录在 sys.path[0] 而可用。
"""
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from PIL import Image

SRC = Path(__file__).parent.parent / "src"


def run(mod: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SRC / mod), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def run_ok(mod: str, *args: str) -> subprocess.CompletedProcess:
    """运行脚本并断言成功；失败时把 stdout/stderr 带进断言消息方便排查。"""
    r = run(mod, *args)
    assert r.returncode == 0, (
        f"{mod} 失败 (exit {r.returncode})\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    return r


def make_img(path: Path, w: int = 100, h: int = 100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (0, 0, 0)).save(path)


def make_two_tone(path: Path, w: int, h: int, top_color, bottom_color) -> None:
    """生成上下两色的图（用于校验混合/拼接的方向）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = top_color if y < h // 2 else bottom_color
    img.save(path)


def _region_matches(img: Image.Image, box, color, tol: int = 12) -> bool:
    """img 中 box 区域是否整块近似为 color（容差 tol 应对 JPEG 有损）。"""
    from PIL import ImageChops

    region = img.crop(box)
    expected = Image.new("RGB", region.size, color)
    diff = ImageChops.difference(region, expected)
    return all(ext[1] <= tol for ext in diff.getextrema())


def test_double_page_crop_split_and_idempotency(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    make_img(d / "spread.png", 200, 80)   # 比例 2.5 -> 双页
    make_img(d / "single.png", 80, 200)   # 比例 0.4 -> 单页

    run_ok("double_page_crop.py", str(d))
    split = d.parent / "in_split"
    assert sorted(p.name for p in split.iterdir()) == [
        "single.png",
        "spread_01.png",
        "spread_02.png",
    ]

    # 再跑一次：已拆分的 _01/_02 不应被重复拆分
    run_ok("double_page_crop.py", str(split))
    assert sorted(p.name for p in split.iterdir()) == [
        "single.png",
        "spread_01.png",
        "spread_02.png",
    ]


def test_double_page_crop_does_not_overwrite_existing(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    make_img(d / "single.png", 80, 200)

    out = d.parent / "in_split"
    out.mkdir()
    (out / "single.png").write_bytes(b"old")  # 输出目录里同名文件已存在

    r = run_ok("double_page_crop.py", str(d))
    assert "跳过" in r.stdout
    assert (out / "single.png").read_bytes() == b"old"  # 未被覆盖


def test_volume_split_negative_page_count_reported(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    for n in ["1.png", "2.png", "3.png"]:
        make_img(d / n, 10, 10)
    # 目录页后只有 2 页，但声明的跨度是 10 页 -> 最后一章页数算出来是负数
    (tmp_path / "contents.txt").write_text("1 第一章 1\n2 第二章 11\n", encoding="utf-8")

    r = run("volume_split_into_chapters.py", str(d), "1.png", str(tmp_path / "contents.txt"))
    assert r.returncode != 0
    assert "页数" in r.stdout and "-8" in r.stdout


def test_volume_split(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    for n in ["1.png", "2.png", "3.png", "4.png", "5.png"]:
        make_img(d / n, 10, 10)
    (tmp_path / "contents.txt").write_text("1 第一章 1\n2 第二章 3\n", encoding="utf-8")

    run_ok("volume_split_into_chapters.py", str(d), "2.png", str(tmp_path / "contents.txt"))
    out = d.parent / "in_split"
    ch1 = out / "1 第一章"
    ch2 = out / "2 第二章"
    assert ch1.is_dir() and ch2.is_dir()
    assert len(list(ch1.iterdir())) == 2
    assert len(list(ch2.iterdir())) == 1


def test_volume_split_zero_page_chapter_counts_correctly(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    for n in ["1.png", "2.png", "3.png", "4.png", "5.png", "6.png"]:
        make_img(d / n, 10, 10)
    # 第一章与第二章起始页相同 -> 第一章 0 页；目录页是 2.png，其后共 4 页内容
    (tmp_path / "contents.txt").write_text("1 空章 1\n2 第一章 1\n3 第二章 3\n", encoding="utf-8")

    run_ok("volume_split_into_chapters.py", str(d), "2.png", str(tmp_path / "contents.txt"))
    out = d.parent / "in_split"
    assert len(list((out / "1 空章").iterdir())) == 0
    assert len(list((out / "2 第一章").iterdir())) == 2
    assert len(list((out / "3 第二章").iterdir())) == 2


def test_volume_split_title_and_cn_number_formats(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    for n in ["1.png", "2.png", "3.png", "4.png", "5.png", "6.png", "7.png"]:
        make_img(d / n, 10, 10)
    # 覆盖 docstring 承诺的另外两种写法：纯标题、中文编号标题；目录页是 2.png，其后共 5 页
    (tmp_path / "contents.txt").write_text("特别篇 1\n第二章 3\n", encoding="utf-8")

    run_ok("volume_split_into_chapters.py", str(d), "2.png", str(tmp_path / "contents.txt"))
    out = d.parent / "in_split"
    assert sorted(p.name for p in (out / "特别篇").iterdir()) == ["3.png", "4.png"]
    assert sorted(p.name for p in (out / "第二章").iterdir()) == ["5.png", "6.png", "7.png"]


def test_cn_numbers_rename_prefix(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第3话 测试").mkdir(parents=True)
    (d / "第十二话 x").mkdir(parents=True)
    (d / "已经01 别的").mkdir(parents=True)

    run_ok("cn_numbers_rename.py", "--style", "prefix", str(d))
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

    run_ok("cn_numbers_rename.py", "--style", "replace", str(d))
    assert sorted(p.name for p in d.iterdir()) == [
        "2 测试",
        "5",
        "第 3 条 备注",
    ]


def test_cn_numbers_rename_conflict_skips_and_fails(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第二话 测试").mkdir(parents=True)
    (d / "2 测试").mkdir(parents=True)  # 已存在与改名结果同名的目录

    r = run("cn_numbers_rename.py", "--style", "replace", str(d))
    assert r.returncode == 1
    assert (d / "第二话 测试").is_dir()   # 未被覆盖
    assert (d / "2 测试").is_dir()


def test_cn_numbers_rename_prefix_idempotent(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第3话 xxx").mkdir(parents=True)
    (d / "第七条 yyy").mkdir(parents=True)

    # 加过前缀的名字不再命中"第X话/条"开头，重复运行应保持不变
    run_ok("cn_numbers_rename.py", "--style", "prefix", str(d))
    run_ok("cn_numbers_rename.py", "--style", "prefix", str(d))
    assert sorted(p.name for p in d.iterdir()) == [
        "0 第3话 xxx",
        "1 第七条 yyy",
    ]


def test_cn_numbers_rename_prefix_conflict_skips(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第3话 xxx").mkdir(parents=True)
    (d / "0 第3话 xxx").mkdir(parents=True)  # 已存在将要生成的目标名

    r = run("cn_numbers_rename.py", "--style", "prefix", str(d))
    assert r.returncode == 1  # 有跳过 -> 视为失败
    assert sorted(p.name for p in d.iterdir()) == ["0 第3话 xxx", "第3话 xxx"]


def test_cn_numbers_rename_prefix_orders_by_chapter_number(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第3话 xxx").mkdir(parents=True)
    (d / "第七条 yyy").mkdir(parents=True)
    (d / "第10话 zzz").mkdir(parents=True)
    (d / "第一百零八话 w").mkdir(parents=True)

    run_ok("cn_numbers_rename.py", "--style", "prefix", str(d))
    assert [p.name for p in sorted(d.iterdir())] == [
        "0 第3话 xxx",
        "1 第七条 yyy",
        "2 第10话 zzz",
        "3 第一百零八话 w",
    ]


def test_generate_source_file(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "01话集.mp3").write_text("x")
    (d / "第3话 测试.txt").write_text("x")
    (d / "10话.txt").write_text("x")

    run_ok("generate_source_file.py", str(d))
    lines = (d / "source.txt").read_text(encoding="utf-8").splitlines()
    assert lines == ["1 话集.mp3", "3 测试.txt", "10 话.txt"]


def test_generate_source_file_conflict_keeps_files(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    # "1话.txt" 与 "01话.txt" 会映射到同一个新名字，重命名应跳过而不是覆盖
    (d / "1话.txt").write_text("a")
    (d / "01话.txt").write_text("b")

    r = run("generate_source_file.py", str(d))
    assert r.returncode != 0
    names = set(p.name for p in d.iterdir())
    assert "source.txt" in names
    assert "1 话.txt" in names                    # 一个成功改名
    assert len(names) == 3                        # 另一个保留原名，未被覆盖


def test_chapter_pages_rename_by_order_root_and_subdirs(tmp_path: Path):
    top = tmp_path / "top"
    sub = top / "sub"
    sub.mkdir(parents=True)
    for n in ["a.jpg", "b.jpg"]:
        (top / n).write_text("x")
        (sub / n).write_text("x")

    r = run_ok("chapter_pages_rename_by_order.py", str(top))
    assert sorted(p.name for p in top.iterdir() if p.is_file()) == ["00.jpg", "01.jpg"]
    assert sorted(p.name for p in sub.iterdir()) == ["00.jpg", "01.jpg"]
    assert '"a.jpg" -> "00.jpg"' in r.stdout  # 日志应显示原文件名


def test_chapter_pages_rename_by_order_dry_run_keeps_files(tmp_path: Path):
    top = tmp_path / "top"
    top.mkdir()
    for n in ["a.jpg", "b.jpg"]:
        (top / n).write_text("x")

    r = run_ok("chapter_pages_rename_by_order.py", "-n", str(top))
    assert sorted(p.name for p in top.iterdir()) == ["a.jpg", "b.jpg"]
    assert "预览" in r.stdout
    assert '"a.jpg" -> "00.jpg"' in r.stdout


def test_pages_organize(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    make_img(d / "abc_12_34.jpg")

    run_ok("pages_organize_into_chapters.py", str(d))
    assert (d / "12" / "abc_12_34.jpg").is_file()


def test_pages_organize_conflict_skips(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    make_img(d / "abc_12_34.jpg")
    dest = d / "12"
    dest.mkdir()
    (dest / "abc_12_34.jpg").write_bytes(b"old")

    run_ok("pages_organize_into_chapters.py", str(d))
    assert (d / "abc_12_34.jpg").is_file()                    # 原文件未被移动
    assert (dest / "abc_12_34.jpg").read_bytes() == b"old"    # 未被覆盖


def test_check_page_width_all_match(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    make_img(d / "a.png", 800, 100)
    make_img(d / "b.png", 800, 100)

    r = run_ok("check_page_width.py", str(d))
    assert "所有图片宽度均为 800" in r.stdout


def test_check_page_width_mismatch_exits_nonzero(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    make_img(d / "a.png", 800, 100)
    make_img(d / "b.png", 800, 100)
    make_img(d / "c.png", 600, 100)

    r = run("check_page_width.py", str(d))
    assert r.returncode == 1
    assert "c.png" in r.stdout


def test_unzip_all(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    make_img(d / "img1.jpg", 10, 10)
    zip_path = d / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(d / "img1.jpg", "img1.jpg")
    (d / "img1.jpg").unlink()

    run_ok("unzip_all.py", str(d))
    assert (d / "book" / "img1.jpg").is_file()


def test_unzip_all_duplicate_names_skipped(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    zip_path = d / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a/img1.jpg", b"first")
        zf.writestr("b/img1.jpg", b"second")  # 拍平后与前者同名

    run_ok("unzip_all.py", str(d))
    target = d / "book"
    assert [p.name for p in target.iterdir()] == ["img1.jpg"]
    assert (target / "img1.jpg").read_bytes() == b"first"  # 先到先得，后者跳过


def test_unzip_all_bad_zip_continues(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "book.zip").write_bytes(b"not a zip")

    run_ok("unzip_all.py", str(d))  # 坏 zip 报错跳过，不应崩溃
    assert not (d / "book").exists()


def test_unzip_all_no_archives_is_ok(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "a.jpg").write_bytes(b"x")

    r = run_ok("unzip_all.py", str(d))
    assert "未找到" in r.stdout


def test_unzip_all_empty_zip_leaves_no_dir(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    with zipfile.ZipFile(d / "book.zip", "w") as zf:
        zf.writestr("readme.txt", "no images")

    run_ok("unzip_all.py", str(d))
    assert not (d / "book").exists()  # 没有图片就不该留下空文件夹


def test_unzip_all_accepts_cbz(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    with zipfile.ZipFile(d / "book.cbz", "w") as zf:
        zf.writestr("img1.jpg", b"img")

    run_ok("unzip_all.py", str(d))
    assert (d / "book" / "img1.jpg").is_file()


def test_zip_all(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir(parents=True, exist_ok=True)
    sub = d / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    make_img(sub / "a.jpg", 10, 10)

    run_ok("zip_all.py", str(d))
    zp = d / "sub.zip"
    assert zp.is_file()
    with zipfile.ZipFile(zp) as zf:
        assert "sub/a.jpg" in zf.namelist()


def test_page_blender(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    # a: 上红下黑；b: 上黑下蓝。-u 50 应取 a 上半 + b 下半
    RED, BLACK, BLUE = (255, 0, 0), (0, 0, 0), (0, 0, 255)
    make_two_tone(a, 100, 100, RED, BLACK)
    make_two_tone(b, 100, 100, BLACK, BLUE)

    run_ok("page_blender.py", "-u", "50", str(a), str(b))
    out = tmp_path / "result_up_50.png"
    assert out.is_file()
    img = Image.open(out)
    assert img.size == (100, 100)                     # 尺寸不变
    assert _region_matches(img, (0, 0, 100, 50), RED)   # 上半来自 a
    assert _region_matches(img, (0, 50, 100, 100), BLUE)  # 下半来自 b


def test_page_blender_rejects_negative_number(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    make_img(a, 100, 100)
    make_img(b, 100, 100)

    r = run("page_blender.py", "-u", "-50", str(a), str(b))
    assert r.returncode != 0


def test_page_concat(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    RED, BLUE = (255, 0, 0), (0, 0, 255)
    Image.new("RGB", (100, 100), RED).save(a)   # a 整张红
    Image.new("RGB", (100, 100), BLUE).save(b)  # b 整张蓝

    run_ok("page_concat.py", "-H", str(a), str(b))
    out = list(tmp_path.glob("merged_*.png"))
    assert out, "应生成拼接结果"
    img = Image.open(out[0])
    assert img.size == (200, 100)                       # 横向拼接尺寸
    assert _region_matches(img, (0, 0, 100, 100), RED)    # 左半来自 a
    assert _region_matches(img, (100, 0, 200, 100), BLUE)  # 右半来自 b


def test_page_concat_vertical(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    RED, BLUE = (255, 0, 0), (0, 0, 255)
    Image.new("RGB", (100, 100), RED).save(a)
    Image.new("RGB", (100, 100), BLUE).save(b)

    run_ok("page_concat.py", "-V", str(a), str(b))
    out = list(tmp_path.glob("merged_*.png"))
    assert out
    img = Image.open(out[0])
    assert img.size == (100, 200)                       # 竖向拼接尺寸
    assert _region_matches(img, (0, 0, 100, 100), RED)     # 上半来自 a
    assert _region_matches(img, (0, 100, 100, 200), BLUE)  # 下半来自 b


def test_page_concat_output_next_to_first_image(tmp_path: Path):
    # 两张图在不同目录时，输出应落在第一张图所在目录（不能按字符串公共前缀猜）
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    make_img(d1 / "a.png", 50, 50)
    make_img(d2 / "b.png", 50, 50)

    run_ok("page_concat.py", "-H", str(d1 / "a.png"), str(d2 / "b.png"))
    assert list(d1.glob("merged_*.png"))
    assert not list(d2.glob("merged_*.png"))


def test_page_concat_missing_input_exits_nonzero(tmp_path: Path):
    r = run("page_concat.py", "-H", str(tmp_path / "nope1.png"), str(tmp_path / "nope2.png"))
    assert r.returncode != 0


def test_page_concat_size_mismatch_exits_nonzero(tmp_path: Path):
    make_img(tmp_path / "a.png", 100, 100)
    make_img(tmp_path / "b.png", 100, 80)

    r = run("page_concat.py", "-H", str(tmp_path / "a.png"), str(tmp_path / "b.png"))
    assert r.returncode != 0
    assert "高度" in r.stdout


def test_hentai_zip_rename_inside(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    zip_path = d / "mycomic.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("oldname/a.txt", "hello")

    run_ok("hentai_zip_rename_inside.py", str(d))
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.startswith("mycomic/") for n in names)


def test_hentai_zip_rename_inside_ignores_stale_tmp_zip(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    # 模拟上次运行失败残留的临时文件，不应被当作输入处理
    stale = d / "book.tmp.zip"
    stale.write_bytes(b"garbage")

    r = run("hentai_zip_rename_inside.py", str(d))
    assert r.returncode == 0
    assert stale.read_bytes() == b"garbage"  # 原样保留，未被改动


def test_hentai_zip_rename_inside_preserves_mac_tags(tmp_path: Path):
    import _common  # 测试进程里直接用 _common 打标签（SRC 已在 sys.path，见 conftest/pythonpath）

    d = tmp_path / "p"
    d.mkdir()
    zip_path = d / "mycomic.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("oldname/a.txt", "hello")
    if _common.set_mac_tags(zip_path, ["Red"]) is not True:
        pytest.skip("macOS 标签不可用")  # 非 macOS 或 pyobjc 缺失

    run_ok("hentai_zip_rename_inside.py", str(d))
    # 原子替换会用没有标签的新文件覆盖原包，所以标签必须在替换前搬到临时包上
    assert _common.get_mac_tags(zip_path) == ["Red"]


def test_hentai_zip_rename_inside_excludes_hidden(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    zip_path = d / "mycomic.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("oldname/a.txt", "hello")
        zf.writestr("oldname/.DS_Store", "junk")
        zf.writestr("__MACOSX/oldname/._junk", "junk")  # mac zip 常见附带物

    run_ok("hentai_zip_rename_inside.py", str(d))
    with zipfile.ZipFile(zip_path) as zf:
        # 隐藏文件被排除；__MACOSX 不干扰"解压出单个文件夹"的判定，重命名正常发生
        assert zf.namelist() == ["mycomic/a.txt"]


def test_keywords_searching(tmp_path: Path):
    parent = tmp_path / "imgs"
    sub = parent / "sub"
    sub.mkdir(parents=True)
    make_img(sub / "img1.jpg", 10, 10)

    ocr = tmp_path / "ocr"
    ocr_sub = ocr / "sub"
    ocr_sub.mkdir(parents=True)
    (ocr_sub / "img1.jpg.json").write_text(json.dumps({"texts": "hello keyword world"}), encoding="utf-8")

    run_ok("keywords_searching.py", str(parent), str(ocr), "keyword")
    out = tmp_path / "keyword_output"
    assert out.is_dir()
    jpgs = list(out.rglob("*.jpg"))
    assert jpgs, "keyword_output 中应有匹配图片"


def test_keywords_searching_dry_run_no_side_effects(tmp_path: Path):
    parent = tmp_path / "imgs"
    sub = parent / "sub"
    sub.mkdir(parents=True)
    make_img(sub / "img1.jpg", 10, 10)

    ocr = tmp_path / "ocr"
    ocr_sub = ocr / "sub"
    ocr_sub.mkdir(parents=True)
    (ocr_sub / "img1.jpg.json").write_text(json.dumps({"texts": "hello keyword world"}), encoding="utf-8")

    run_ok("keywords_searching.py", "-n", str(parent), str(ocr), "keyword")
    assert (parent / "sub" / "img1.jpg").is_file()   # 图片未被移动
    assert not (tmp_path / "keyword_output").exists()  # 未创建输出目录


def test_jpeg_2_jpg(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "a.JPEG").write_bytes(b"x")
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "b.jpeg").write_bytes(b"x")
    (d / "keep.txt").write_bytes(b"x")

    run_ok("jpeg_2_jpg.py", str(d))
    assert not (d / "a.JPEG").exists()
    assert not (d / "sub" / "b.jpeg").exists()
    assert (d / "a.jpg").is_file()
    assert (d / "sub" / "b.jpg").is_file()
    assert (d / "keep.txt").is_file()  # 非 jpeg 不受影响


def test_jpeg_2_jpg_missing_dir_exits_nonzero(tmp_path: Path):
    r = run("jpeg_2_jpg.py", str(tmp_path / "nope"))
    assert r.returncode == 1


def test_jpeg_2_jpg_skip_when_target_exists(tmp_path: Path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "a.jpeg").write_bytes(b"jpeg")
    (d / "a.jpg").write_bytes(b"jpg")  # 已存在同名 jpg，应跳过

    run_ok("jpeg_2_jpg.py", str(d))
    assert (d / "a.jpeg").is_file()  # 未改名
    assert (d / "a.jpg").read_bytes() == b"jpg"  # 未被覆盖


def test_primage_wrapper_missing_file(tmp_path: Path):
    r = run("primage_wrapper.py", str(tmp_path / "nope.png"), "jpg")
    assert r.returncode == 1
    assert "不存在" in r.stdout


def test_primage_wrapper_same_ext_skip(tmp_path: Path):
    img = tmp_path / "a.jpg"
    (img).write_bytes(b"x")
    r = run_ok("primage_wrapper.py", str(img), "jpg")
    assert "一致" in r.stdout


def test_primage_wrapper_convert(tmp_path: Path):
    img = tmp_path / "a.png"
    make_img(img, 20, 20)
    run_ok("primage_wrapper.py", str(img), "jpg")
    out = tmp_path / "a.jpg"
    assert out.is_file()
    assert Image.open(out).format == "JPEG"


def test_convert_image_format_to(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    make_img(d / "a.png", 20, 20)
    make_img(d / "b.png", 20, 20)

    run_ok("convert_image_format_to.py", "jpg", str(d))
    out = tmp_path / "result" / "in"
    assert out.is_dir()
    assert sorted(p.name for p in out.iterdir()) == ["a.jpg", "b.jpg"]
    assert Image.open(out / "a.jpg").format == "JPEG"


def test_convert_image_format_to_invalid_format_exits_nonzero(tmp_path: Path):
    r = run("convert_image_format_to.py", "bmp", str(tmp_path))
    assert r.returncode != 0


def test_batch_convert_avif_all_avif_shortcut(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    zip_path = d / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("page1.avif", b"dummy")  # 仅按扩展名判定，无需真实 avif

    run_ok("batch_convert_image_format_inside_zip_to_avif.py", str(d))
    out_zip = tmp_path / "result" / "book.cbz"
    assert out_zip.is_file()        # 已复制到输出目录（无需转换）
    assert zip_path.is_file()       # 原文件保留
    with zipfile.ZipFile(out_zip) as zf:
        assert zf.namelist() == ["page1.avif"]


def test_batch_convert_avif_converts(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    inner = d / "book"
    inner.mkdir()
    make_img(inner / "a.jpg", 20, 20)
    zip_path = d / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(inner / "a.jpg", "a.jpg")
    shutil.rmtree(inner)

    run_ok("batch_convert_image_format_inside_zip_to_avif.py", str(d))
    out_zip = tmp_path / "result" / "book.cbz"
    assert out_zip.is_file()
    with zipfile.ZipFile(out_zip) as zf:
        # 万能入口保留包内原始目录结构，不再额外套一层包名文件夹
        assert zf.namelist() == ["a.avif"]


def test_batch_convert_avif_no_images_fails(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    with zipfile.ZipFile(d / "book.zip", "w") as zf:
        zf.writestr("readme.txt", "no images here")

    r = run("batch_convert_image_format_inside_zip_to_avif.py", str(d))
    assert r.returncode != 0


def test_batch_convert_avif_failure_raises(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    inner = d / "book"
    inner.mkdir()
    (inner / "bad.jpg").write_text("not a real image")  # primage 无法解码
    zip_path = d / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(inner / "bad.jpg", "bad.jpg")
    shutil.rmtree(inner)

    r = run("batch_convert_image_format_inside_zip_to_avif.py", str(d))
    assert r.returncode != 0


def test_convert_single_image_file(tmp_path: Path):
    img = tmp_path / "a.png"
    make_img(img, 20, 20)
    run_ok("convert_image_format_to.py", "jpg", str(img))
    out = tmp_path / "result" / "a.jpg"
    assert out.is_file()
    assert Image.open(out).format == "JPEG"


def test_convert_single_archive(tmp_path: Path):
    inner = tmp_path / "book"
    inner.mkdir()
    make_img(inner / "a.jpg", 20, 20)
    zip_path = tmp_path / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(inner / "a.jpg", "ch01/a.jpg")
    shutil.rmtree(inner)

    run_ok("convert_image_format_to.py", "avif", str(zip_path))
    out_zip = tmp_path / "result" / "book.cbz"
    assert out_zip.is_file()
    with zipfile.ZipFile(out_zip) as zf:
        assert zf.namelist() == ["ch01/a.avif"]


def test_convert_single_cbz(tmp_path: Path):
    make_img(tmp_path / "a.jpg", 20, 20)
    cbz_path = tmp_path / "book.cbz"
    with zipfile.ZipFile(cbz_path, "w") as zf:
        zf.write(tmp_path / "a.jpg", "a.jpg")

    run_ok("convert_image_format_to.py", "avif", str(cbz_path))
    out_cbz = tmp_path / "result" / "book.cbz"
    assert out_cbz.is_file()
    with zipfile.ZipFile(out_cbz) as zf:
        assert zf.namelist() == ["a.avif"]


def test_convert_archives_batch_dir(tmp_path: Path):
    d = tmp_path / "in"
    d.mkdir()
    make_img(d / "a.jpg", 20, 20)
    with zipfile.ZipFile(d / "book.zip", "w") as zf:
        zf.write(d / "a.jpg", "a.jpg")

    run_ok("convert_image_format_to.py", "avif", str(d))
    out_dir = tmp_path / "result"
    assert (out_dir / "book.cbz").is_file()
    with zipfile.ZipFile(out_dir / "book.cbz") as zf:
        assert zf.namelist() == ["a.avif"]
    # 最外层散图也顺手转了
    assert (out_dir / "a.avif").is_file()


def _clear_utf8_flags(src_zip: Path, dst_zip: Path) -> None:
    """清掉 local(+6) 与 central(+8) 两处 UTF-8 标记，模拟缺标记的压包工具出的坏包。"""
    import struct

    data = bytearray(src_zip.read_bytes())
    i = 0
    while True:
        i = data.find(b"PK\x03\x04", i)
        if i < 0:
            break
        struct.pack_into("<H", data, i + 6, struct.unpack_from("<H", data, i + 6)[0] & ~0x800)
        i += 4
    i = 0
    while True:
        i = data.find(b"PK\x01\x02", i)
        if i < 0:
            break
        struct.pack_into("<H", data, i + 8, struct.unpack_from("<H", data, i + 8)[0] & ~0x800)
        i += 4
    dst_zip.write_bytes(data)


def test_convert_single_archive_fixes_missing_utf8_flag_names(tmp_path: Path):
    """缺 UTF-8 标记的中文包：日志不再乱码，输出包内恢复中文名并带上标记。"""
    inner = tmp_path / "01 刑期二十年"
    inner.mkdir()
    make_img(inner / "00.jpg", 20, 20)
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(inner / "00.jpg", "01 刑期二十年/00.jpg")
    bad = tmp_path / "01 刑期二十年.zip"
    _clear_utf8_flags(good, bad)
    with zipfile.ZipFile(bad) as zf:
        assert zf.infolist()[0].flag_bits == 0  # 确认坏包造出来了

    r = run_ok("convert_image_format_to.py", "avif", str(bad))
    assert "01 刑期二十年/00.avif" in r.stdout  # 日志是中文而非 σêæ… 乱码

    out_zip = tmp_path / "result" / "01 刑期二十年.cbz"
    assert out_zip.is_file()
    with zipfile.ZipFile(out_zip) as zf:
        assert zf.namelist() == ["01 刑期二十年/00.avif"]
        assert zf.infolist()[0].flag_bits & 0x800  # 输出是规范的 UTF-8 包


def test_unzip_all_fixes_missing_utf8_flag_names(tmp_path: Path):
    """unzip_all 拍平时取包内中文名：坏包也应落盘中文名。"""
    inner = tmp_path / "src"
    inner.mkdir()
    make_img(inner / "封面.jpg", 10, 10)
    good = tmp_path / "p" / "book.zip"
    good.parent.mkdir()
    with zipfile.ZipFile(good, "w") as zf:
        zf.write(inner / "封面.jpg", "第1话/封面.jpg")
    bad = tmp_path / "p" / "bad.zip"
    _clear_utf8_flags(good, bad)
    good.unlink()

    run_ok("unzip_all.py", str(tmp_path / "p"))
    assert (tmp_path / "p" / "bad" / "封面.jpg").is_file()


def test_hentai_polish_folder(tmp_path: Path):
    d = tmp_path / "doujin"
    d.mkdir()
    for i in range(1, 13):
        make_img(d / f"{i}.jpg", 20, 20)
    (d / "notes.txt").write_text("ignore me")  # 非图片应被跳过

    run_ok("hentai_polish.py", str(d))
    out = tmp_path / "result" / "doujin.cbz"
    assert out.is_file()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert names == [f"{i:02d}.avif" for i in range(1, 13)]  # 总数 12 → 宽 2 位
        assert all(zf.getinfo(n).file_size > 0 for n in names)


def test_hentai_polish_archive_order(tmp_path: Path):
    for n in ("cover.png", "p1.jpg", "p2.jpg", "p10.jpg"):
        make_img(tmp_path / n, 20, 20)
    zip_path = tmp_path / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for n in ("cover.png", "p1.jpg", "p2.jpg", "p10.jpg"):
            zf.write(tmp_path / n, n)

    run_ok("hentai_polish.py", str(zip_path))
    out = tmp_path / "result" / "book.cbz"
    assert out.is_file()
    with zipfile.ZipFile(out) as zf:
        # 总数 4 → 宽 1 位；cover < p1 < p2 < p10（自然排序）
        assert zf.namelist() == ["1.avif", "2.avif", "3.avif", "4.avif"]


def test_hentai_polish_batch(tmp_path: Path):
    d = tmp_path / "A"
    d.mkdir()
    make_img(d / "a.jpg", 20, 20)
    make_img(d / "b.jpg", 20, 20)
    with zipfile.ZipFile(d / "b1.zip", "w") as zf:
        zf.write(d / "a.jpg", "a.jpg")
        zf.write(d / "b.jpg", "b.jpg")
    with zipfile.ZipFile(d / "b2.zip", "w") as zf:
        zf.write(d / "a.jpg", "x.jpg")

    run_ok("hentai_polish.py", str(d))
    out_dir = tmp_path / "result"
    with zipfile.ZipFile(out_dir / "b1.cbz") as zf:
        assert zf.namelist() == ["1.avif", "2.avif"]
    with zipfile.ZipFile(out_dir / "b2.cbz") as zf:
        assert zf.namelist() == ["1.avif"]
    # 散图单独打成一包
    with zipfile.ZipFile(out_dir / "A.cbz") as zf:
        assert zf.namelist() == ["1.avif", "2.avif"]


def test_hentai_polish_failure_produces_no_output(tmp_path: Path):
    d = tmp_path / "doujin"
    d.mkdir()
    make_img(d / "1.jpg", 20, 20)
    (d / "2.jpg").write_text("not a real image")  # primage 无法解码 -> 转换失败

    r = run("hentai_polish.py", str(d))
    assert r.returncode != 0
    # 有转换失败时不输出（不产出残缺的 cbz），原输入保留
    assert not (tmp_path / "result" / "doujin.cbz").exists()
    assert (d / "1.jpg").is_file() and (d / "2.jpg").is_file()


def test_binsync_generates_all_shims(tmp_path: Path):
    """全仓库唯一的命令生成器 tools/binsync.py（各子项目分散的生成器已并入）。"""
    binsync = SRC.parent / "tools" / "binsync.py"
    r = subprocess.run(
        [sys.executable, str(binsync), "--out", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr

    # src/ 下的 python 脚本统一走 uv 垫片
    shim = tmp_path / "hentai-polish"
    assert shim.is_file()
    assert shim.stat().st_mode & 0o111  # 有执行位
    text = shim.read_text(encoding="utf-8")
    assert "src/hentai_polish.py" in text
    assert "--project" in text
    assert '"$@"' in text
    assert "DO NOT EDIT" in text

    # 原 other/ 的零依赖脚本与原 shell 脚本都并入 src 走 uv
    assert "src/format_xhtml.py" in (tmp_path / "format-xhtml").read_text(encoding="utf-8")
    assert "src/compress_epub.py" in (
        tmp_path / "compress-epub").read_text(encoding="utf-8")
    assert "src/workbuddy_checkin.py" in (
        tmp_path / "workbuddy-checkin").read_text(encoding="utf-8")

    # 老别名已删除：统一用 cn-numbers-rename（replace 风格手动加 --style replace）
    assert not (tmp_path / "convert-chinese-numbers-to-arab").exists()
    assert not (tmp_path / "convert-cn-numbers-to-arab").exists()
    assert (tmp_path / "cn-numbers-rename").is_file()
    # 下划线开头的模块不生成命令
    assert not (tmp_path / "_common").exists()
    assert not (tmp_path / "_binsync").exists()

    # --check 在已同步时不报差异；改动后能检出
    r = subprocess.run(
        [sys.executable, str(binsync), "--out", str(tmp_path), "--check"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    (tmp_path / "zip-all").unlink()
    r = subprocess.run(
        [sys.executable, str(binsync), "--out", str(tmp_path), "--check"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 1


# ── bangumi_rename（按 source.txt 猜集数重命名）────────────────────────────
SOURCE_24 = "\n".join(f"{i:02d} 标题{i}" for i in range(1, 25)) + "\n"


def _bangumi(tmp_path: Path, names: list, source: str = SOURCE_24, *extra: str):
    """建目录 + source.txt，dry-run 跑 bangumi_rename，返回 (结果, 目录)。"""
    d = tmp_path / "p"
    d.mkdir()
    for n in names:
        (d / n).touch()
    src = tmp_path / "source.txt"
    src.write_text(source, encoding="utf-8")
    return run_ok("bangumi_rename.py", "-s", str(src), "-d", str(d), "-n", *extra), d


def test_bangumi_rename_sxxeyy(tmp_path: Path):
    """S02E01 这类：季号 02 恒定被淘汰，CRC 里的 E1 不得误判为集数。"""
    names = [
        f"[LostYears] One Punch Man - S02E{i:02d} (WEB 1080p x264 10-bit AAC) [{0x3288FA84 + i:08X}].ass"
        for i in range(1, 13)
    ]
    r, _ = _bangumi(tmp_path, names)
    assert "待确认" not in r.stdout, r.stdout      # 12 个全都有把握
    for i in range(1, 13):
        assert f'S02E{i:02d} ' in r.stdout and f'-> "{i:02d} 标题{i}.ass"' in r.stdout, r.stdout


def test_bangumi_rename_ep_marker(tmp_path: Path):
    """Ep.287：Part/Vol 恒定被淘汰，选出 Ep. 后的数字。"""
    names = [
        "[NAOKI-Raws] 名探偵コナン／Part.11-Vol.1 Ep.001 「x」 (DVDRip x264 AC3).ass",
        "[NAOKI-Raws] 名探偵コナン／Part.11-Vol.1 Ep.011 「x」 (DVDRip x264 AC3).ass",
        "[NAOKI-Raws] 名探偵コナン／Part.11-Vol.1 Ep.012 「x」 (DVDRip x264 AC3).ass",
    ]
    r, _ = _bangumi(tmp_path, names)
    assert "待确认" not in r.stdout, r.stdout
    assert 'Ep.011' in r.stdout and '-> "11 标题11.ass"' in r.stdout, r.stdout


def test_bangumi_rename_bracket_number(tmp_path: Path):
    """[01] 孤立数字槽：分辨率 2160 与码率 10bit 都被淘汰。"""
    names = [f"[DBD-Raws][龙珠大魔][{i:02d}][2160P][UHDBDRip][HEVC-10bit][FLAC].mkv"
             for i in range(1, 21)]
    r, _ = _bangumi(tmp_path, names)
    assert "待确认" not in r.stdout, r.stdout
    assert '-> "20 标题20.mkv"' in r.stdout, r.stdout


def test_bangumi_rename_cn_number(tmp_path: Path):
    """中文数字序号：转成阿拉伯后按真实集数对应，不是按字符串顺序。"""
    names = ["[组] 番剧 第一话.mkv", "[组] 番剧 第三话.mkv", "[组] 番剧 第二话.mkv"]
    r, _ = _bangumi(tmp_path, names)
    assert "待确认" not in r.stdout, r.stdout
    assert '第三话.mkv" -> "03 标题3.mkv"' in r.stdout, r.stdout
    assert '第二话.mkv" -> "02 标题2.mkv"' in r.stdout, r.stdout


def test_bangumi_rename_range_in_dirname(tmp_path: Path):
    """文件名里没有可变集数（2160p 恒定）时，用目录名的 01-03 区间按顺序分配。"""
    d = tmp_path / "[DBD-Raws][龙珠大魔][01-03TV全集][2160P][HEVC-10bit]"
    d.mkdir()
    for lang in ("粤语", "国语", "日语"):
        (d / f"龙珠大魔 2160p UHDBDRip {lang}.mkv").touch()
    src = tmp_path / "source.txt"
    src.write_text(SOURCE_24, encoding="utf-8")
    r = run_ok("bangumi_rename.py", "-s", str(src), "-d", str(d), "-n")
    assert "按目录区间" in r.stdout, r.stdout
    # 中文按 Unicode 排序：国语 < 日语 < 粤语
    assert '国语.mkv" -> "01 标题1.mkv"' in r.stdout, r.stdout
    assert '粤语.mkv" -> "03 标题3.mkv"' in r.stdout, r.stdout


def test_bangumi_rename_order_mode(tmp_path: Path):
    """--order + --start：不猜集数，按排序从指定集数开始一一对应。"""
    names = [f"video_{i}.mkv" for i in range(1, 6)]
    r, _ = _bangumi(tmp_path, names, SOURCE_24, "--order", "--start", "5")
    assert 'video_1.mkv" -> "05 标题5.mkv"' in r.stdout, r.stdout
    assert 'video_5.mkv" -> "09 标题9.mkv"' in r.stdout, r.stdout


def test_bangumi_rename_pending_not_renamed(tmp_path: Path):
    """没把握的默认不改名；文件名压根没数字的，--force 也无从下手。"""
    names = ["莫名其妙的名字.mkv", "另一个没数字的.mkv"]
    r, d = _bangumi(tmp_path, names)
    assert "2 项待确认" in r.stdout, r.stdout
    assert sorted(p.name for p in d.iterdir()) == sorted(names)   # 保持原名

    r2 = run_ok("bangumi_rename.py", "-s", str(tmp_path / "source.txt"),
                "-d", str(d), "-n", "--force")
    assert "文件名无数字，无从改名" in r2.stdout, r2.stdout
    assert "将重命名 0 项" in r2.stdout, r2.stdout   # 不能谎报已处理
    assert "--order" in r2.stdout, r2.stdout         # 要给出可操作的下一步


def test_bangumi_rename_force_uses_top_candidate(tmp_path: Path):
    """--force 对「有候选但两个候选同分、不敢定夺」的项，按最高分改名。"""
    # 两个孤立数字槽 [01] 与 [02] 同分 → margin=0 → 判定没把握
    names = ["莫名其妙的名字.mkv", "[01] [02] mix.mkv"]
    r, d = _bangumi(tmp_path, names)
    assert "将重命名 0 项" in r.stdout, r.stdout      # 默认不猜

    r2 = run_ok("bangumi_rename.py", "-s", str(tmp_path / "source.txt"),
                "-d", str(d), "-n", "--force")
    assert '"[01] [02] mix.mkv" -> "01 标题1.mkv"' in r2.stdout, r2.stdout
    assert "将重命名 1 项" in r2.stdout, r2.stdout     # force 让它真的改了
    assert "文件名无数字" in r2.stdout, r2.stdout     # 另一项如实报告


def test_bangumi_rename_bracket_slot_is_confident(tmp_path: Path):
    """单个孤立数字槽（[DBD-Raws]…[01]… 的核心特征）应自信识别，不该进待确认。"""
    names = [f"[DBD-Raws][4K_SDR][Dragon Ball Daima][{i:02d}][2160P][UHDBDRip][HEVC-10bit][FLAC].mkv"
             for i in range(1, 7)]
    r, _ = _bangumi(tmp_path, names)
    assert "待确认" not in r.stdout, r.stdout
    assert '[01][2160P]' in r.stdout and '-> "01 标题1.mkv"' in r.stdout, r.stdout


def test_bangumi_rename_idempotent(tmp_path: Path):
    """实际执行后重复运行应为空操作（已对上的名字跳过）。"""
    d = tmp_path / "p"
    d.mkdir()
    for i in range(1, 6):
        (d / f"[组] 番剧 第{i}话.mkv").touch()
    src = tmp_path / "source.txt"
    src.write_text(SOURCE_24, encoding="utf-8")
    run_ok("bangumi_rename.py", "-s", str(src), "-d", str(d))
    assert sorted(p.name for p in d.iterdir()) == [f"{i:02d} 标题{i}.mkv" for i in range(1, 6)]

    r = run_ok("bangumi_rename.py", "-s", str(src), "-d", str(d))
    assert "已重命名 0 项" in r.stdout, r.stdout


def test_bangumi_rename_unsafe_title_chars(tmp_path: Path):
    """标题里的 / 会让 with_name 抛错，必须替换成全角。"""
    d = tmp_path / "p"
    d.mkdir()
    (d / "[组] 番剧 第1话.mkv").touch()
    src = tmp_path / "source.txt"
    src.write_text("1 与17年前一样的案发现场 B/F\n", encoding="utf-8")
    r = run_ok("bangumi_rename.py", "-s", str(src), "-d", str(d))
    assert "非法字符" in r.stdout, r.stdout
    assert (d / "1 与17年前一样的案发现场 B／F.mkv").is_file()


def test_bangumi_rename_ext_filter_and_folders(tmp_path: Path):
    """-e 只处理指定扩展名；--folders 处理子目录名。"""
    d = tmp_path / "p"
    d.mkdir()
    (d / "[组] 番剧 第1话.mkv").touch()
    (d / "[组] 番剧 第2话.ass").touch()
    src = tmp_path / "source.txt"
    src.write_text(SOURCE_24, encoding="utf-8")
    run_ok("bangumi_rename.py", "-s", str(src), "-d", str(d), "-e", "mkv")
    assert (d / "01 标题1.mkv").is_file()
    assert (d / "[组] 番剧 第2话.ass").is_file()      # 未被处理

    d2 = tmp_path / "q"
    d2.mkdir()
    (d2 / "第3话 某章").mkdir()
    run_ok("bangumi_rename.py", "-s", str(src), "-d", str(d2), "--folders")
    assert (d2 / "03 标题3").is_dir()


def test_bangumi_rename_folders_recursive(tmp_path: Path):
    """--folders + -R：子目录改名后旧路径失效，不能预先 rglob 收集（会 FileNotFoundError）。"""
    d = tmp_path / "r"
    for i in (1, 2):
        (d / f"第{i}话 某章").mkdir(parents=True)
    (d / "第3话 某章" / "inner").mkdir(parents=True)
    src = tmp_path / "source.txt"
    src.write_text(SOURCE_24, encoding="utf-8")
    r = run_ok("bangumi_rename.py", "-s", str(src), "-d", str(d), "--folders", "-R")
    assert r.returncode == 0
    assert (d / "01 标题1").is_dir()
    assert (d / "02 标题2").is_dir()
    assert (d / "03 标题3" / "inner").is_dir()   # 嵌套层也遍历到，未崩
