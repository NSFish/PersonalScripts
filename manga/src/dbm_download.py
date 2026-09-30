#!/usr/bin/env python3
"""下载龙珠超次元乱战（Dragon Ball Multiverse）中文版，按话存图并打包 CBZ。

只用标准库：uv run --project manga dbm-download [--chapters 1-10] [--dest 目录]

流程：抓 chapters.html 解析每话的 page 链接 -> 逐页抓 page-N.html 取
#balloonsimg 里 /image.php?...&pw=... 真图 -> 按话存入 第001话_标题/NNNN.jpg
-> 每话打成 .cbz。支持断点续下（已存在且非空的图片跳过）。

⚠️ 站点已逐页改版为「CSS 背景图(无字原画) + HTML balloon 文字层」新格式，
本脚本的 <img> 正则对新格式页会错误抓到社交图标。新格式页请用
dbm_fix.py（headless 浏览器渲染方案）。判断方法：下载结果出现 256x256
等小图标即该页被污染，记下页码后用 dbm_fix.py 修复。
"""
import argparse
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://www.dragonball-multiverse.com"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def fetch(url: str, referer: str | None = None, retries: int = 8) -> bytes:
    headers = dict(UA)
    if referer:
        headers["Referer"] = referer
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - 网络抖动直接重试
            last = e
            time.sleep(min(2 ** i, 30))  # 指数退避：1,2,4,8,16,30...
    raise RuntimeError(f"下载失败 {url}: {last}")


def get_chapters(lang: str) -> list[tuple[str, list[int]]]:
    """返回 [(话标题, [页号...]), ...]，页号按导航页顺序去重保序。"""
    url = f"{BASE}/{lang}/chapters.html?comic=page"
    html = fetch(url).decode("utf-8", errors="ignore")
    out = []
    for title, p in re.findall(r"<h4>(Chapter \d+:.*?)</h4>\s*<p>(.*?)</p>", html, re.S):
        nums = []
        for href in re.findall(r'href="(page-(\d+)\.html)"', p):
            n = int(href[1])
            if n not in nums:
                nums.append(n)
        title = re.sub(r"<[^>]+>", "", title).strip()
        out.append((title, nums))
    return out


def parse_range(s: str | None, total: int) -> list[int]:
    if not s:
        return list(range(1, total + 1))
    sel: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            sel.update(range(int(a), int(b) + 1))
        elif part:
            sel.add(int(part))
    return sorted(i for i in sel if 1 <= i <= total)


def clean(s: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', "_", s).strip()[:100]


def main() -> None:
    parser = argparse.ArgumentParser(description="下载龙珠超次元乱战中文版并按话打包 CBZ")
    parser.add_argument("--lang", default="cn", help="语言（默认 cn）")
    parser.add_argument("--chapters", default=None, help="只下指定话，如 1-10 或 3,5,7")
    parser.add_argument("--dest", default=str(Path.home() / "Downloads" / "龙珠超次元乱战"),
                        help="落盘目录")
    parser.add_argument("--delay", type=float, default=0.4, help="每页间隔秒数")
    parser.add_argument("--no-cbz", action="store_true", help="只存图片不打包")
    args = parser.parse_args()

    chapters = get_chapters(args.lang)
    print(f"共 {len(chapters)} 话")
    dest = Path(args.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    for idx in parse_range(args.chapters, len(chapters)):
        title, pages = chapters[idx - 1]
        dirname = f"第{idx:03d}话_{clean(title)}"
        d = dest / dirname
        d.mkdir(exist_ok=True)
        ok = 0
        for n in pages:
            out = d / f"{n:04d}.jpg"
            if out.exists() and out.stat().st_size > 0:
                ok += 1
                continue
            page_url = f"{BASE}/{args.lang}/page-{n}.html"
            html = fetch(page_url).decode("utf-8", errors="ignore")
            m = re.search(r'id="balloonsimg"[^>]*>.*?<img[^>]*src="([^"]+)"', html, re.S)
            if not m:
                print(f"  [warn] 第{idx}话 page-{n} 未找到图片，跳过")
                continue
            src = m.group(1)
            img_url = BASE + src if src.startswith("/") else src
            data = fetch(img_url, referer=page_url)
            out.write_bytes(data)
            ok += 1
            time.sleep(args.delay)
        print(f"[{idx}/{len(chapters)}] {dirname}: {ok}/{len(pages)} 页")
        if not args.no_cbz:
            cbz = dest / f"{dirname}.cbz"
            with zipfile.ZipFile(cbz, "w", zipfile.ZIP_STORED) as z:
                for img in sorted(d.glob("*.jpg")):
                    z.write(img, img.name)
            print(f"  -> {cbz.name} ({cbz.stat().st_size // 1024} KB)")

    print("done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("中断，已下好的图片保留，可重跑续下")
