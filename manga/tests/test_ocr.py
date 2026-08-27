"""ocr_process 的回归测试：用 macOS Vision 对带文字的图片做 OCR，校验输出 JSON。

仅在 macOS（pyobjc + Vision 可用）下运行；其它平台用 importorskip 跳过。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

Vision = pytest.importorskip("Vision")

from PIL import Image, ImageDraw, ImageFont

from _common import is_image_file  # 顺带确认脚本依赖可导入

FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"


def _make_text_image(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(FONT, 40)
    img = Image.new("RGB", (400, 120), (255, 255, 255))
    ImageDraw.Draw(img).text((10, 30), text, fill=(0, 0, 0), font=font)
    img.save(path)


def test_ocr_process_writes_texts_json(tmp_path: Path):
    if not Path(FONT).exists():
        pytest.skip("缺少系统字体，跳过 OCR 测试")

    parent = tmp_path / "imgs"
    sub = parent / "sub"
    sub.mkdir(parents=True)
    _make_text_image(sub / "a.jpg", "OCR Test 42")

    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "src" / "ocr_process.py"), str(parent)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr

    out = parent.parent / "imgs_ocr_result" / "sub" / "a.jpg.json"
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "OCR" in data["texts"] and "42" in data["texts"]
