"""manga 脚本的功能回归测试：用临时目录真实运行各脚本，校验输出。

通过 subprocess 调用 venv 内的 python（即运行 pytest 的解释器）执行 manga/src 下的脚本，
脚本内 `from _common import ...` 因脚本目录在 sys.path[0] 而可用。
"""
import json
import shutil
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


def test_chapter_pages_rename_by_order(tmp_path: Path):
    sub = tmp_path / "top" / "sub"
    sub.mkdir(parents=True)
    for n in ["a.jpg", "b.jpg", "c.jpg"]:
        (sub / n).write_text("x")

    r = run_ok("chapter_pages_rename_by_order.py", str(tmp_path / "top"))
    assert sorted(p.name for p in sub.iterdir()) == ["00.jpg", "01.jpg", "02.jpg"]
    assert '"a.jpg" -> "00.jpg"' in r.stdout  # 日志应显示原文件名


def test_insert_numbers(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第3话 xxx").mkdir(parents=True)
    (d / "第七条 yyy").mkdir(parents=True)

    run_ok("insert_numbers_in_front_of_chapter_titles.py", str(d))
    assert sorted(p.name for p in d.iterdir()) == [
        "0 第3话 xxx",
        "1 第七条 yyy",
    ]


def test_insert_numbers_idempotent(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第3话 xxx").mkdir(parents=True)
    (d / "第七条 yyy").mkdir(parents=True)

    run_ok("insert_numbers_in_front_of_chapter_titles.py", str(d))
    run_ok("insert_numbers_in_front_of_chapter_titles.py", str(d))
    assert sorted(p.name for p in d.iterdir()) == [
        "0 第3话 xxx",
        "1 第七条 yyy",
    ]


def test_insert_numbers_conflict_skips(tmp_path: Path):
    d = tmp_path / "p"
    (d / "第3话 xxx").mkdir(parents=True)
    (d / "0 第3话 xxx").mkdir(parents=True)  # 已存在将要生成的目标名

    run_ok("insert_numbers_in_front_of_chapter_titles.py", str(d))
    assert sorted(p.name for p in d.iterdir()) == ["0 第3话 xxx", "第3话 xxx"]


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


def test_page_concat_missing_input_exits_nonzero(tmp_path: Path):
    r = run("page_concat.py", "-H", str(tmp_path / "nope1.png"), str(tmp_path / "nope2.png"))
    assert r.returncode != 0


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
    out = tmp_path / "in_jpg"
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
    out_zip = tmp_path / "in_avif" / "book.zip"
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
    out_zip = tmp_path / "in_avif" / "book.zip"
    assert out_zip.is_file()
    with zipfile.ZipFile(out_zip) as zf:
        assert zf.namelist() == ["book/a.avif"]


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
