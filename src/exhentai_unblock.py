#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exhentai_unblock.py — 修复 exhentai.org 白屏（只删坏 cookie，保留登录状态）。

背景：
    exhentai.org 会给被拉黑的出口 IP 下发 `igneous=mystery`，
    此后浏览器只要带着这个值请求，服务器一律返回 0 字节空白页（白屏）。
    关键点：这个坏 cookie **不会自愈**——即使换成干净的 IP，
    只要请求里还带着 igneous=mystery，依然白屏。
    所以每次换代理节点后都必须先删掉它，否则会误判成"新节点也不行"。

用法:
  python3 src/exhentai_unblock.py check           # 只检查当前节点，不改任何东西
  python3 src/exhentai_unblock.py fix             # 节点干净时：退浏览器 → 删 igneous
  python3 src/exhentai_unblock.py fix --launch    # 同上，结束后自动重开浏览器
  python3 src/exhentai_unblock.py fix --force     # 节点被拉黑也照删（一般不用）

  --browser edge|chrome  选择浏览器（默认 edge，找不到登录 cookie 时自动试另一个）
  --proxy URL            指定代理，默认读系统代理设置

退出码:
  0 正常 / 已修复
  1 节点被拉黑，需要换节点
  2 环境问题（找不到登录 cookie、浏览器退不掉、代理不通等）

依赖：仅标准库 + 系统自带 openssl / security / curl。
"""
import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from export_cookies import BROWSERS, read_cookies

TARGET_HOST = ".exhentai.org"
EX_URL = "https://exhentai.org/"
LOGIN_COOKIES = ("ipb_member_id", "ipb_pass_hash")
BAD_IGNEOUS = "mystery"

# 浏览器 → 用于判断"是否在运行"与退出的进程特征 / 应用名
PROCESS = {
    "edge": ("Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "Microsoft Edge"),
    "chrome": ("Google Chrome.app/Contents/MacOS/Google Chrome", "Google Chrome"),
}

OK = "✅"
FAIL = "❌"
WARN = "⚠️"
INFO = "💡"


# ------------------------------------------------------------------ 代理

def system_proxy() -> str | None:
    """从系统网络设置读 HTTP 代理，读不到返回 None。"""
    try:
        out = subprocess.run(["scutil", "--proxy"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return None
    if "HTTPEnable : 1" not in out:
        return None
    host = re.search(r"HTTPProxy : (\S+)", out)
    port = re.search(r"HTTPPort : (\d+)", out)
    if host and port:
        return f"http://{host.group(1)}:{port.group(1)}"
    return None


# ------------------------------------------------------------------ 探测

def probe(proxy: str | None, cookies: dict[str, str]) -> tuple:
    """请求 exhentai，返回 (状态码, 实际下载字节数, 下发的 igneous 值)。

    注意：exhentai 用 chunked 传输、不返回 content-length，
    字节数必须取 curl 的 size_download，不能读响应头。
    """
    ck = "; ".join(f"{k}={v}" for k, v in cookies.items())
    hdr = tempfile.NamedTemporaryFile(delete=False, suffix=".hdr")
    hdr.close()
    try:
        cmd = ["curl", "-s", "-o", "/dev/null", "-D", hdr.name,
               "-w", "%{http_code} %{size_download}",
               "--max-time", "25", "-H", f"Cookie: {ck}", EX_URL]
        if proxy:
            cmd[1:1] = ["-x", proxy]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        if r.returncode != 0:
            return None, 0, None

        parts = r.stdout.strip().split()
        code = int(parts[0]) if parts and parts[0].isdigit() else None
        size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

        headers = Path(hdr.name).read_text(errors="replace")
        ign = None
        m = re.search(r"^set-cookie:\s*igneous=([^;\r\n]+)", headers, re.M | re.I)
        if m:
            ign = m.group(1).strip()
        return code, size, ign
    finally:
        os.unlink(hdr.name)


def verdict(code: int | None, size: int, ign: str | None) -> tuple[str, str]:
    """把探测结果翻译成 (状态, 人话)。状态取 ok / banned / bad。"""
    if code is None:
        return "bad", "连不上 exhentai（代理没开？节点挂了？）"
    if ign == BAD_IGNEOUS:
        return "banned", "节点被拉黑：服务器下发了 igneous=mystery"
    if size == 0:
        return "banned", "服务器返回 0 字节空白页（等价于被拉黑）"
    if ign:
        return "ok", f"节点正常，下发了新 igneous={ign}（有效期 30 天）"
    return "ok", "节点正常"


# ------------------------------------------------------------------ 浏览器进程

def is_running(browser: str) -> bool:
    pattern, _ = PROCESS[browser]
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True,
                          timeout=10).returncode == 0


def quit_browser(browser: str) -> bool:
    """退出浏览器并确认真的退了（否则它会写回旧 cookie，等于白删）。"""
    pattern, app = PROCESS[browser]
    subprocess.run(["osascript", "-e", f'tell application "{app}" to quit'],
                   capture_output=True, timeout=30)
    for _ in range(20):
        if not is_running(browser):
            return True
        time.sleep(0.5)
    subprocess.run(["pkill", "-f", pattern], capture_output=True, timeout=15)
    time.sleep(1)
    return not is_running(browser)


def launch_browser(browser: str) -> None:
    _, app = PROCESS[browser]
    subprocess.run(["open", "-a", app], capture_output=True, timeout=30)


# ------------------------------------------------------------------ cookie 增删

def cookie_db(browser: str) -> Path:
    return Path(os.path.expanduser(BROWSERS[browser][0]))


def delete_bad_igneous(browser: str) -> tuple[int, list[str]]:
    """只删 igneous，保留登录 cookie。返回 (删除条数, 剩下的 cookie 名)。"""
    db = cookie_db(browser)
    backup = db.with_suffix(db.suffix + ".bak_exh")
    shutil.copy2(db, backup)
    con = sqlite3.connect(db)
    try:
        cur = con.execute(
            "DELETE FROM cookies WHERE host_key = ? AND name = 'igneous'",
            (TARGET_HOST,))
        n = cur.rowcount
        con.commit()
        left = [r[0] for r in con.execute(
            "SELECT name FROM cookies WHERE host_key = ?", (TARGET_HOST,))]
    finally:
        con.close()
    return n, left


def pick_browser(preferred: str) -> tuple[str | None, dict[str, str]]:
    """挑一个已登录 exhentai 的浏览器，返回 (名字, cookie 字典)。"""
    order = [preferred] + [b for b in BROWSERS if b != preferred]
    for name in order:
        cookies = {c["name"]: c["value"]
                   for c in read_cookies(name, (TARGET_HOST,))}
        if cookies and all(k in cookies for k in LOGIN_COOKIES):
            return name, cookies
    return None, {}


# ------------------------------------------------------------------ 命令

def cmd_check(proxy: str | None, args) -> int:
    browser, cookies = pick_browser(args.browser)
    if not browser:
        print(f"{FAIL} 没找到 exhentai 的登录 cookie（ipb_member_id / ipb_pass_hash）。")
        print(f"{INFO} 先在一个浏览器里正常登录 e-hentai.org，再来跑。")
        return 2

    print(f"代理: {proxy or '（未使用）'}")
    print(f"cookie 来源: {browser}，已登录账号 {cookies['ipb_member_id']}")
    if "igneous" in cookies:
        shown = f"{BAD_IGNEOUS}（坏的）" if cookies["igneous"] == BAD_IGNEOUS else "正常哈希"
        print(f"浏览器里的 igneous: {shown}")

    clean = {k: v for k, v in cookies.items() if k != "igneous"}
    code, size, ign = probe(proxy, clean)
    state, msg = verdict(code, size, ign)
    mark = OK if state == "ok" else FAIL
    print(f"探测结果: HTTP {code}, {size} 字节")
    print(f"判断: {mark} {msg}")

    if state == "ok" and cookies.get("igneous") == BAD_IGNEOUS:
        print()
        print(f"{WARN} 节点是干净的，但浏览器里还留着 igneous={BAD_IGNEOUS}，")
        print("   它会让你继续白屏。跑 `exhentai-unblock fix` 删掉即可。")
    return 0 if state == "ok" else 1


def cmd_fix(proxy: str | None, args) -> int:
    browser, cookies = pick_browser(args.browser)
    if not browser:
        print(f"{FAIL} 没找到 exhentai 的登录 cookie，无法判断节点状态。")
        return 2

    clean = {k: v for k, v in cookies.items() if k != "igneous"}
    code, size, ign = probe(proxy, clean)
    state, msg = verdict(code, size, ign)
    mark = OK if state == "ok" else FAIL
    print(f"节点: {mark} {msg}")

    if state == "bad":
        print()
        print(f"{FAIL} 连不上 exhentai，先确认代理客户端在运行、节点可用。")
        return 2
    if state == "banned" and not args.force:
        print()
        print(f"{FAIL} 节点被拉黑，删 cookie 也没用。先在代理里换一个干净节点，")
        print(f"{INFO} 换完再跑一次 `exhentai-unblock check`。")
        return 1

    if is_running(browser):
        print(f"退出 {browser}…")
        if not quit_browser(browser):
            print(f"{FAIL} 退不掉 {browser}，请手动退出后重试（否则会写回旧 cookie）。")
            return 2
        time.sleep(1)

    n, left = delete_bad_igneous(browser)
    if n:
        print(f"{OK} 已删除 igneous，保留: {', '.join(left) or '（无）'}")
    else:
        print(f"{OK} {browser} 里本来就没有 igneous，无需删除。")

    print()
    print(f"{OK} 完成。重新打开浏览器访问 {EX_URL} 即可。")
    print(f"{INFO} 若节点干净，服务器会自动下发新的 igneous，有效期 30 天。")

    if args.launch:
        launch_browser(browser)
        print(f"{OK} 已重新打开 {browser}。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="exhentai-unblock",
        description="修复 exhentai.org 白屏（只删坏掉的 igneous，保留登录状态）",
    )
    ap.add_argument("action", choices=["check", "fix"],
                    help="check 只诊断；fix 诊断并删除坏 cookie")
    ap.add_argument("--browser", choices=sorted(BROWSERS), default="edge",
                    help="优先使用的浏览器（默认 edge）")
    ap.add_argument("--proxy", default=None,
                    help="代理地址，如 http://127.0.0.1:7890；默认读系统代理")
    ap.add_argument("--launch", action="store_true", help="修复后重新打开浏览器")
    ap.add_argument("--force", action="store_true", help="节点被拉黑时也执行删除")
    args = ap.parse_args()

    proxy = args.proxy or system_proxy()
    if args.action == "check":
        return cmd_check(proxy, args)
    return cmd_fix(proxy, args)


if __name__ == "__main__":
    sys.exit(main())
