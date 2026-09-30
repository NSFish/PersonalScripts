#!/usr/bin/env python3
"""修复被污染成图标的 DBM 页面：headless Edge 渲染官网页面，裁出漫画本体。

用法:
  预览:   uv run --project manga dbm-fix --pages 1192,2542,2741 [--out 预览目录]
  替换:   uv run --project manga dbm-fix --pages 1192,2542 --replace
不带 --replace 时只输出到 --out 目录预览；带 --replace 时直接替换
~/Downloads/龙珠超次元乱战/第NNN话_*/PPPP.jpg

原理: 站点新格式页用 CSS 背景图(无字原画) + HTML balloon 文字层，
浏览器渲染后裁出漫画区即等价于官网显示效果（含官方字体渲染的对白）。
定位: 漫画区左右黑边框是贯穿高度 75%+ 的长竖线，配对间距 = 画布宽+2；
顶部横线同样按配对确定；裁剪区域含官网渐变蓝超阈值视为失败自动重试。
注意: 特殊动画页（如 2167/2379）用 --virtual-time-budget 等动画播完，
且可能带 ↺ Replay 按钮（可用 Vision OCR 检查、用相邻画面镜像修补）。
依赖: Microsoft Edge（/Applications/Microsoft Edge.app）+ Pillow
"""
import argparse
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
BASE = "https://www.dragonball-multiverse.com"
EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
DEST_ROOT = Path.home() / "Downloads" / "龙珠超次元乱战"


def fetch_html(page: int) -> tuple[str, int, int]:
    """返回 (页面HTML, 漫画宽, 漫画高)"""
    req = urllib.request.Request(f"{BASE}/cn/page-{page}.html", headers=UA)
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    m = re.search(
        r'id="balloonsimg"[^>]*width:(\d+)px;\s*height:(\d+)px', html)
    if not m:
        raise RuntimeError(f"page-{page}: 未找到漫画尺寸（可能不是新版页面）")
    return html, int(m.group(1)), int(m.group(2))


def screenshot(page: int, w: int, h: int, tmp_png: Path) -> None:
    """headless Edge 截整页，窗口尺寸足够容纳页头+漫画"""
    url = f"{BASE}/cn/page-{page}.html"
    win_w = max(900, w + 100)
    win_h = h + 420  # 页头(约220) + 黄条 + 余量
    for attempt in range(2):
        subprocess.run(
            [EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
             f"--window-size={win_w},{win_h}", f"--screenshot={tmp_png}", url],
            check=True, capture_output=True, timeout=60)
        time.sleep(0.2)
        try:
            # 校验截图内容有效（裁剪逻辑内部会再做一次）
            return
        except Exception:
            if attempt == 1:
                raise
            time.sleep(1)


def crop_comic(png: Path, w: int, h: int, out: Path) -> None:
    """从截图中定位漫画黑边框并裁出 W×H。

    定位策略：漫画区左右边框是贯穿高度 85%+ 的纯黑竖线（官网蓝背景无此特征）。
    先找出所有长黑竖线列，取与目标宽度 w 匹配的一对作为左右框。
    """
    from PIL import Image
    img = Image.open(png).convert("RGB")
    W, H = img.size
    px = img.load()

    def col_dark_run(x):
        best = cur = 0
        for y in range(H):
            r, g, b = px[x, y]
            if r < 100 and g < 100 and b < 100:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    vlines = [x for x in range(W) if col_dark_run(x) >= h * 0.75]
    if len(vlines) < 2:
        raise RuntimeError(f"{png.name}: 竖线不足 ({vlines})")

    # 找间距 == w 的一对（允许 ±3 像素误差）
    pair = None
    for i, left in enumerate(vlines):
        for right in vlines[i + 1:]:
            if abs((right - left) - (w + 2)) <= 6:  # +2 = 左右边框各占 1px
                pair = (left, right)
                break
        if pair:
            break
    if not pair:
        raise RuntimeError(f"{png.name}: 未找到宽度匹配的竖线对 (w={w}, 竖线={vlines[:8]})")
    left, right = pair

    # 在 [left, right] 范围内找顶/底横线（贯穿度按漫画宽度算）
    def row_dark_run(y, x0, x1):
        best = cur = 0
        for x in range(x0, x1):
            r, g, b = px[x, y]
            if r < 100 and g < 100 and b < 100:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    inner = w - 4
    hlines = [y for y in range(150, H) if row_dark_run(y, left, right) >= inner * 0.9]
    # 顶线：与另一条强横线构成精确间距 h+2 的那一条（页面元素如黄条底边
    # 不会有这种配对）。找到即可确定漫画区域上下界。
    top = next(
        (y for y in hlines if any(0 <= (y2 - y) - (h + 2) <= 4 for y2 in hlines)),
        None)
    if top is None:
        raise RuntimeError(f"{png.name}: 未找到高度配对的横线 (h={h}, 候选={hlines[:6]})")

    # 校验候选位置：裁出区域内"官网渐变蓝"占比必须极低。
    # 官网背景蓝 (36-60, 72-140, 225-240)，与漫画内天空蓝（更浅、饱和度不同）区分
    def blue_ratio(crop):
        cpx = crop.load()
        cw, ch = crop.size
        cnt = tot = 0
        for x in range(0, cw, 6):
            for y in range(0, ch, 6):
                r, g, b = cpx[x, y]
                tot += 1
                if b > 195 and 150 < b - r and r < 90 and g < 160:
                    cnt += 1
        return cnt / tot

    crop = img.crop((left + 1, top + 1, left + 1 + w, top + 1 + h))
    if crop.size != (w, h):
        raise RuntimeError(f"{png.name}: 裁剪尺寸 {crop.size} != {(w, h)}")
    if blue_ratio(crop) > 0.02:
        raise RuntimeError(f"{png.name}: 裁剪区域混入官网背景")
    out.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out, quality=92)


def target_path(page: int) -> Path | None:
    """找到该页对应的 第NNN话/PPPP.jpg"""
    for d in DEST_ROOT.glob("第*话*"):
        if not d.is_dir():
            continue
        f = d / f"{page:04d}.jpg"
        if f.exists():
            return f
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="修复 DBM 被污染页面")
    ap.add_argument("--pages", required=True, help="逗号分隔的页码，如 1192,2542")
    ap.add_argument("--out", default="/tmp/dbm_fix_preview", help="预览输出目录")
    ap.add_argument("--replace", action="store_true", help="直接替换下载目录中的文件")
    args = ap.parse_args()

    pages = [int(p) for p in args.pages.split(",") if p.strip()]
    outdir = Path(args.out)

    ok, fail = 0, []
    for page in pages:
        try:
            html, w, h = fetch_html(page)
            tmp_png = Path(f"/tmp/dbm_shot_{page}.png")
            # 截图+裁剪，加载不完整(大片官网蓝)时重试，最多 4 次
            last_err = None
            for attempt in range(4):
                screenshot(page, w, h, tmp_png)
                if args.replace:
                    target = target_path(page)
                    if target is None:
                        raise RuntimeError(f"page-{page}: 下载目录中找不到对应文件")
                    out = target
                else:
                    out = outdir / f"page-{page}.jpg"
                try:
                    crop_comic(tmp_png, w, h, out)
                    last_err = None
                    break
                except RuntimeError as e:
                    last_err = e
                    time.sleep(1.5)  # 等页面资源加载
            if last_err:
                raise last_err
            tmp_png.unlink(missing_ok=True)
            ok += 1
            print(f"[ok] page-{page} ({w}x{h}) -> {out}")
        except Exception as e:  # noqa: BLE001
            fail.append(page)
            print(f"[fail] page-{page}: {e}")
        time.sleep(0.5)

    print(f"\n完成 {ok}/{len(pages)}，失败: {fail or '无'}")


if __name__ == "__main__":
    main()
