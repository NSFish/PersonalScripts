"""hentai_quality_report 的回归测试。

设计要点：
- 判级只依赖可靠指标：等效 dpi / 体积密度 / 尺寸一致性（judge 单测覆盖）；
- detail 是参考指标（画风依赖强，不参与判级），测试它对【同源对比】有效：
  同一母版，放大版必须比原版显著更低（端到端覆盖）；
- 取中值而非均值，这样本子里的平涂扉页/纯白页（detail 天然≈0）不会拖累典型值。

测试用的合成图：1200dpi 母版 → 降采样 = 真扫描，低 dpi 图 → 放大 = 赝品。
"""
import io
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import hentai_quality_report as H
from _common import OUTPUT_DIR_NAME  # noqa: F401  仅确认导入链正常

SRC = Path(__file__).parent.parent / "src"
MM = 25.4
MASTER_DPI = 1200
B5_W, B5_H = 182.0, 257.0


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SRC / "hentai_quality_report.py"), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def canvas(dpi: float) -> tuple[int, int]:
    return (int(round(B5_W / MM * dpi)), int(round(B5_H / MM * dpi)))


_MASTER_CACHE: Image.Image | None = None


def master() -> Image.Image:
    """1200dpi 母版：60lpi 网点 + 线条。

    物理频率固定，故降采样后跨 dpi 仍可比。逐像素绘制很慢，模块级缓存只生成一次。
    """
    global _MASTER_CACHE
    if _MASTER_CACHE is not None:
        return _MASTER_CACHE
    import random

    rnd = random.Random(4)
    w, h = canvas(MASTER_DPI)
    img = Image.new("L", (w, h), 250)
    d = ImageDraw.Draw(img)
    pitch = MASTER_DPI / 60.0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if (round(x / pitch) + round(y / pitch)) % 2 == 0:
                d.point((x, y), fill=rnd.randint(60, 140))
    for _ in range(60):
        x0, y0 = rnd.randint(0, w), rnd.randint(0, h)
        d.line([x0, y0, x0 + rnd.randint(-w // 6, w // 6),
                y0 + rnd.randint(-h // 6, h // 6)], fill=30, width=4)
    _MASTER_CACHE = img
    return img


def jpeg(img: Image.Image, q: int = 90) -> Image.Image:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=q)
    b.seek(0)
    return Image.open(b).convert("L")


_PAGE_CACHE: dict[tuple, Image.Image] = {}


def real_page(dpi: float) -> Image.Image:
    """真扫描：母版降采样（按 dpi 缓存，避免重复缩放 1200dpi 母版）"""
    key = ("real", dpi)
    if key not in _PAGE_CACHE:
        _PAGE_CACHE[key] = jpeg(master().resize(canvas(dpi), Image.LANCZOS))
    return _PAGE_CACHE[key]


def fake_page(dpi: float, src: float) -> Image.Image:
    """AI 赝品：低 dpi 真图放大到目标 dpi"""
    key = ("fake", dpi, src)
    if key not in _PAGE_CACHE:
        _PAGE_CACHE[key] = jpeg(jpeg(master().resize(canvas(src), Image.LANCZOS))
                                .resize(canvas(dpi), Image.LANCZOS))
    return _PAGE_CACHE[key]


def color_page(dpi: float) -> Image.Image:
    """彩色页：三通道明显不同（不过 jpeg()，它会 convert("L") 抹掉色彩）"""
    import random as _r

    rnd = _r.Random(11)
    w, h = canvas(dpi)
    im = Image.new("RGB", (w, h), (255, 250, 245))
    d = ImageDraw.Draw(im)
    for _ in range(40):
        x0, y0 = rnd.randint(0, w - 2), rnd.randint(0, h - 2)
        d.rectangle([x0, y0, rnd.randint(x0 + 1, w), rnd.randint(y0 + 1, h)],
                    fill=(rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90)
    b.seek(0)
    return Image.open(b)  # 保持 RGB


def gray_page(dpi: float) -> Image.Image:
    """灰度页：真实黑白漫画（L 模式）"""
    return real_page(dpi)


def flat_page(dpi: float) -> Image.Image:
    """平涂扉页：无纹理，detail 天然为 0"""
    w, h = canvas(dpi)
    im = Image.new("L", (w, h), 235)
    ImageDraw.Draw(im).rectangle([w // 4, h // 4, 3 * w // 4, 3 * h // 4], fill=180)
    return jpeg(im)


def blank_page(dpi: float) -> Image.Image:
    return jpeg(Image.new("L", canvas(dpi), 252))


def save_book(dst: Path, pages: list[Image.Image]) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(pages, 1):
        p.save(dst / f"{i:03d}.jpg", "JPEG", quality=90)
    return dst


def save_book_pages(dst: Path, sizes: list[tuple[int, int]]) -> Path:
    """按给定尺寸生成页面（带可见纹理，避免被判无纹理）"""
    import random as _r

    rnd = _r.Random(3)
    dst.mkdir(parents=True, exist_ok=True)
    for i, (w, h) in enumerate(sizes, 1):
        im = Image.new("L", (w, h), 250)
        d = ImageDraw.Draw(im)
        for _ in range(40):
            x0, y0 = rnd.randint(0, max(w - 2, 1)), rnd.randint(0, max(h - 2, 1))
            d.rectangle([x0, y0,
                         rnd.randint(min(x0 + 1, w), w),
                         rnd.randint(min(y0 + 1, h), h)],
                        fill=rnd.randint(0, 200))
        im.save(dst / f"{i:04d}.jpg", "JPEG", quality=90)
    return dst


def zip_book(dst: Path, pages: list[Image.Image]) -> Path:
    tmp = dst.parent / f"_t_{dst.stem}"
    save_book(tmp, pages)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_STORED) as zf:
        for p in sorted(tmp.iterdir()):
            zf.write(p, p.name)
    shutil.rmtree(tmp, ignore_errors=True)
    return dst


# ---------------------------------------------------------------- 单元测试 ----
def test_est_dpi_b5_and_spread():
    """竖版按 B5 长边 257mm，横版见開き按 364mm。"""
    w, h = canvas(300)
    assert round(H.est_dpi(w, h, None)) == 300
    # 見開き：364mm 长边，2570px → 约 179dpi
    assert H.est_dpi(3640, 2570, None) == pytest.approx(3640 / (364 / MM), rel=0.01)
    # 手动指定物理长边（A4 297）
    assert H.est_dpi(2480, 3508, 297.0) == pytest.approx(300, rel=0.01)


def test_median():
    assert H.median([]) == 0.0
    assert H.median([3.0]) == 3.0
    assert H.median([1.0, 2.0, 3.0]) == 2.0
    assert H.median([1.0, 2.0, 3.0, 4.0]) == 2.5


def test_sample_indices():
    assert H.sample_indices(10, 0) == list(range(10))
    assert H.sample_indices(4, 8) == [0, 1, 2, 3]
    assert H.sample_indices(10, 1) == [5]
    s = H.sample_indices(10, 3)
    assert s == sorted(set(s)) and len(s) == 3 and 0 in s and 9 in s


def test_build_books_layouts(tmp_path):
    """四种输入结构的识别。"""
    # archives：顶层压缩包各自一本
    root = tmp_path / "zips"
    zip_book(root / "a.cbz", [real_page(300)])
    zip_book(root / "b.cbz", [real_page(300)])
    assert [b.name for b in H.build_books(root, "auto")] == ["a", "b"]

    # books：子文件夹各自一本
    root = tmp_path / "books"
    save_book(root / "x", [real_page(300), real_page(300)])
    save_book(root / "y", [real_page(300)])
    assert [b.name for b in H.build_books(root, "auto")] == ["x", "y"]

    # book：整夹一本（递归收集）
    assert len(H.build_books(root, "book")) == 1

    # 单压缩包 / 单图
    p = zip_book(tmp_path / "s.cbz", [real_page(300)])
    b = H.build_books(p, "auto")
    assert len(b) == 1 and b[0].kind == "archive"
    img = tmp_path / "one.jpg"
    real_page(300).save(img)
    b = H.build_books(img, "auto")
    assert len(b) == 1 and b[0].kind == "image"


def test_build_books_loose_images(tmp_path):
    """有子文件夹本子时，顶层散图额外报一本。"""
    root = tmp_path / "mixed"
    save_book(root / "sub", [real_page(300)])
    real_page(300).save(root / "loose.jpg")
    names = [b.name for b in H.build_books(root, "auto")]
    assert "sub" in names
    assert any("散图" in n for n in names)


def test_unsupported_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(SystemExit):
        H.build_books(f, "auto")


def test_items_from_archive_skips_hidden_and_nonimage(tmp_path):
    p = tmp_path / "b.cbz"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("001.jpg", b"")          # 占位，下面只测条目筛选
        zf.writestr(".DS_Store", b"")
        zf.writestr("__MACOSX/x.jpg", b"")
        zf.writestr("readme.txt", b"")
    items = H.items_from_archive(p)
    assert [it.name for it in items] == ["001.jpg"]


def test_judge_grades():
    """分级只依赖：分辨率 / 尺寸一致性（密度与细节仅提示，不判级）。"""
    # 300dpi + 尺寸一致 → A
    assert H.judge(1.0, 300, 300, False, 0.3, "JPEG")[0] == "A"
    # 200dpi 正常 → B
    assert H.judge(1.0, 200, 300, False, 0.3, "JPEG")[0] == "B"
    # 70dpi → D
    assert H.judge(1.0, 70, 300, False, 0.3, "JPEG")[0] == "D"
    # 尺寸混杂 → 降档
    assert H.judge(0.5, 300, 300, False, 0.3, "JPEG")[0] == "C"
    # 密度低也【不影响】分级（只加提示）—— 这是刻意设计，鉴别力太弱
    g, notes = H.judge(1.0, 300, 5, False, 0.3, "JPEG")
    assert g == "A"
    assert any("密度偏低" in n for n in notes)
    # 黑白/彩色阈值不同：同一密度，灰度达标而彩色不达标
    _, n_gray = H.judge(1.0, 300, 25, False, 0.3, "JPEG")
    _, n_color = H.judge(1.0, 300, 25, True, 0.3, "JPEG")
    assert not any("密度偏低" in n for n in n_gray)
    assert any("密度偏低" in n for n in n_color)
    # AVIF/WEBP 重编码：体积指标跳过
    g, notes = H.judge(1.0, 300, 5, False, 0.3, "AVIF")
    assert any("重编码" in n for n in notes)
    assert not any("密度偏低" in n for n in notes)


# ---------------------------------------------------------------- 端到端 ------
def test_cli_real_vs_fake(tmp_path):
    """端到端：真扫描判级正确；放大赝品的 detail 显著低于真扫描（同源对比有效）。"""
    import json

    root = tmp_path / "lib"
    save_book(root / "真_600dpi", [real_page(600)] * 6 + [flat_page(600), blank_page(600)])
    save_book(root / "真_300dpi", [real_page(300)] * 6 + [flat_page(300)])
    save_book(root / "真_150dpi", [real_page(150)] * 5)
    save_book(root / "赝_放大4x", [fake_page(600, 150)] * 5)
    save_book(root / "赝_放大2x", [fake_page(600, 300)] * 5)

    j = tmp_path / "o.json"
    r = run(str(root), "--sort", "input", "--detail-pages", "5", "--json", str(j))
    assert r.returncode == 0, r.stdout + r.stderr
    data = {x["name"]: x for x in json.loads(j.read_text(encoding="utf-8"))}
    assert data["真_600dpi"]["grade"] == "A"
    assert data["真_300dpi"]["grade"] == "A"
    assert data["真_150dpi"]["grade"] == "C"
    # 注意：赝品按分辨率/密度会拿 A/B —— detail 不参与判级（画风依赖强，会误伤
    # 线稿稀疏的真实数字原生本，如实测的 DL 版）。它的正确用法是同源对比：
    # 同一尺寸(600dpi)下，赝品 detail 至少比真扫描低 3 倍
    real_d = data["真_600dpi"]["detail"]
    for fake in ("赝_放大2x", "赝_放大4x"):
        assert data[fake]["detail"] < real_d / 3, (real_d, data[fake]["detail"])


def test_cli_mixed_color_ratio(tmp_path):
    """黑白本 + 少数彩色表纸：色彩列应报出比例，而不是含糊的『混合』。
    且判级不应因彩页密度低而被拖低（密度只提示，不判级）。"""
    import json

    root = tmp_path / "bw_with_color_cover"
    pages = [color_page(600)] + [gray_page(600)] * 7 + [color_page(600)]
    save_book(root, pages)
    j = tmp_path / "o.json"
    r = run(str(root), "--detail-pages", "4", "--json", str(j))
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(j.read_text(encoding="utf-8"))[0]
    # 8 页抽样：应识别出黑白为主 + 少量彩色，并报出页数
    assert d["color"].startswith("黑白"), d["color"]
    assert "+彩" in d["color"], d["color"]
    # 判级不受彩页拖累（300dpi+ 尺寸一致 → A）
    assert d["grade"] == "A", d


def test_cli_merged_books_detected(tmp_path):
    """上篇+下篇拼在一起：应报『疑似多本合并』并给出第二簇尺寸。"""
    import json

    root = tmp_path / "merged"
    # 上篇 12 页 2000×2800 + 下篇 10 页 1600×2200，两簇都有规模
    save_book_pages(root, [(2000, 2800)] * 12 + [(1600, 2200)] * 10)
    j = tmp_path / "o.json"
    r = run(str(root), "--json", str(j))
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(j.read_text(encoding="utf-8"))[0]
    assert d["merged_size"] == "1600×2200", d
    assert any("多本合并" in n for n in d["notes"]), d["notes"]


def test_cli_single_cover_not_merged(tmp_path):
    """只有一两张异尺寸（表纸/缩略图）不应报『多本合并』。"""
    import json

    root = tmp_path / "withcover"
    save_book_pages(root, [(2000, 2800)] * 20 + [(1200, 1600)])
    j = tmp_path / "o.json"
    r = run(str(root), "--json", str(j))
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(j.read_text(encoding="utf-8"))[0]
    assert d["merged_size"] == "", d
    assert not any("多本合并" in n for n in d["notes"]), d["notes"]


def test_cli_full_scan_consistency(tmp_path):
    """尺寸/色彩按全本统计：抽样撞上异尺寸页不会误报『尺寸混杂』。"""
    import json

    root = tmp_path / "mostly_uniform"
    # 48 页主尺寸 + 3 页异尺寸（占 6%）—— 全查应判尺寸一致
    save_book_pages(root, [(1000, 1400)] * 48 + [(900, 1200)] * 3)
    j = tmp_path / "o.json"
    r = run(str(root), "--json", str(j))
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(j.read_text(encoding="utf-8"))[0]
    assert d["consistent"] > 0.9, d["consistent"]
    assert not any("尺寸混杂" in n for n in d["notes"]), d["notes"]


def test_cli_flat_pages_not_dragged(tmp_path):
    """本子里的平涂/纯白页不该把 detail 拖到 0（中值取典型内容页）。"""
    import json

    root = tmp_path / "withflat"
    save_book(root, [real_page(600)] * 6 + [flat_page(600)] * 3 + [blank_page(600)])
    j = tmp_path / "o.json"
    r = run(str(root), "--detail-pages", "6", "--json", str(j))
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(j.read_text(encoding="utf-8"))[0]
    # 中值应等于真内容页的 detail（~0.26），而不是被 4 页平涂拖低的均值
    bare = json.loads((tmp_path / "bare.json").read_text(encoding="utf-8"))[0] \
        if (tmp_path / "bare.json").exists() else None
    assert data["detail"] > 0.1, data


def test_cli_all_flat_detail_zero(tmp_path):
    """全平涂本：detail 为 0 且不崩溃。"""
    import json

    root = tmp_path / "allflat"
    save_book(root, [blank_page(600)] * 6)
    j = tmp_path / "o.json"
    r = run(str(root), "--detail-pages", "4", "--json", str(j))
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(j.read_text(encoding="utf-8"))[0]
    assert data["detail"] == 0.0
    assert data["detail_pages"] == 0


def test_cli_zip_folder_and_single(tmp_path):
    """压缩包文件夹 / 单个压缩包 两种输入。"""
    root = tmp_path / "zips"
    zip_book(root / "z1.cbz", [real_page(300)] * 4)
    zip_book(root / "z2.cbz", [real_page(300)] * 4)
    r = run(str(root))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "z1" in r.stdout and "z2" in r.stdout

    r = run(str(root / "z1.cbz"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "z1" in r.stdout


def test_cli_json_csv_and_filters(tmp_path):
    """导出与过滤。"""
    root = tmp_path / "lib"
    save_book(root / "hi", [real_page(600)] * 4)
    save_book(root / "lo", [real_page(70)] * 4)
    j, c = tmp_path / "o.json", tmp_path / "o.csv"
    r = run(str(root), "--json", str(j), "--csv", str(c), "--min-grade", "A")
    assert r.returncode == 0, r.stdout + r.stderr
    import csv
    import json

    data = json.loads(j.read_text(encoding="utf-8"))
    assert all(x["grade"] == "A" for x in data)
    with open(c, encoding="utf-8-sig") as fp:
        rows = list(csv.DictReader(fp))
    assert len(rows) == len(data)
    assert {"grade", "detail", "kb_per_mp", "est_dpi"} <= set(rows[0])


def test_cli_bad_zip_and_empty(tmp_path):
    """损坏压缩包 / 空文件夹不崩溃。"""
    bad = tmp_path / "bad.cbz"
    bad.write_bytes(b"not a zip")
    r = run(str(bad))
    assert "损坏" in r.stdout or r.returncode == 1

    empty = tmp_path / "empty"
    empty.mkdir()
    r = run(str(empty))
    assert r.returncode == 1 or "未找到" in r.stdout


def test_cli_mixed_sizes(tmp_path):
    """尺寸混杂应被标注（混入一张不同尺寸的彩页）。"""
    root = tmp_path / "mixed"
    odd = real_page(300).resize((1200, 1600), Image.LANCZOS)  # 明显不同的尺寸
    save_book(root, [real_page(300)] * 3 + [odd])
    r = run(str(root))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "尺寸混杂" in r.stdout or "异尺寸" in r.stdout, r.stdout
