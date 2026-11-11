#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dsh_cookie_clean.py — 清理 DeepSeek Harness 堆积的 dsh-auth cookie。

背景（2026-11 实测）
--------------------
Harness 每次启动，Host 都在一个随机端口上签发一个 dsh-auth cookie。cookie 名
由 authority（"127.0.0.1:<port>"）哈希而来，而端口每次启动都变：

    cookieName(authority) → "dsh-auth-" + sha256(authority)

于是 Chromium 的 cookie 库里每条记录名字都不同 —— 旧记录不会被新记录覆盖，
服务端给的 Max-Age 又是 30 天，旧 cookie 在有效期内一直有效，只进不出。

Chromium 的 net.fetch 会把 cookie 库里所有匹配 127.0.0.1 的 cookie 全塞进
Cookie: 请求头。累计超过 Node HTTP 服务端的 http.maxHeaderSize（16384）后，
服务端直接回 431 Request Header Fields Too Large，Electron 侧拿到非 2xx，
抛出 "desktop welcome: Web authentication failed"，应用启动失败。

实测边界：cookie 头 16200 字节 → 401（正常）；16384 字节 → 431（被拒）。
崩溃那一刻是 70 条旧 cookie 约 15.9 KB，加真实请求头约 350 字节 = 16.5 KB。

清理规则
--------
  - host_key = 127.0.0.1 且名字以 dsh-auth- 开头的记录 → 只留最新 1 条
  - 其余 host / 其余 cookie 名字 → 一律不动

不备份
------
这个库里只有 dsh-auth cookie，每条都随启动端口变化而失效，没有跨启动的价值；
实测把整个库删光应用也照常启动（Host 每次都会签发新的）。所以不留备份文件。
安全网靠"先改临时文件 → 校验 → 原子替换"，写回失败就把原库挪回去。

注意
----
必须在 DeepSeek Harness 未运行时执行 —— Chromium 持锁时改写数据库会损坏它。

用法
----
  dsh-cookie-clean                 # 需要先退出 Harness，直接清理
  dsh-cookie-clean --dry-run       # 只报告条数与字节，不改任何东西
  dsh-cookie-clean --keep 3        # 保留最新 3 条（默认 1）
  dsh-cookie-clean --db 路径        # 指向别的 cookie 库（测试用）

退出码：
  0 正常 / 已清理
  1 环境问题（数据库找不到、Harness 正在运行等）

依赖：仅标准库。
"""
import argparse
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

APP_NAME = "DeepSeek Harness"
COOKIE_HOST = "127.0.0.1"
COOKIE_PREFIX = "dsh-auth-"
DEFAULT_KEEP = 1
# Node 的 http.maxHeaderSize = 16384，留出其余请求头后还能放约 70 条。
# 默认只留 1 条，留足余量。

OK = "✅"
FAIL = "❌"
WARN = "⚠️"
INFO = "💡"


def default_db() -> Path:
    return (Path.home() / "Library/Application Support/@deepseek-ai/dsh-desktop"
            / "Cookies")


def harness_running() -> bool:
    """Harness 是否在运行。Chromium 持锁时不能改数据库。"""
    try:
        r = subprocess.run(["pgrep", "-f", APP_NAME],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _query(db: Path, sql: str, params: tuple = ()) -> list:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        return conn.execute(sql, params).fetchall()


def auth_cookies(db: Path) -> list:
    """列出 dsh-auth cookie：(名字, 创建时间戳, 字节数)，按创建时间新→旧。"""
    rows = _query(
        db,
        "SELECT name, creation_utc, length(name) + length(value) + 3 "
        "  FROM cookies WHERE host_key = ? AND name LIKE ? "
        " ORDER BY creation_utc DESC",
        (COOKIE_HOST, COOKIE_PREFIX + "%"),
    )
    return rows


def total_bytes(db: Path) -> int:
    rows = _query(
        db,
        "SELECT coalesce(sum(length(name) + length(value) + 3), 0) "
        "  FROM cookies WHERE host_key = ? AND name LIKE ?",
        (COOKIE_HOST, COOKIE_PREFIX + "%"),
    )
    return rows[0][0] if rows else 0


def prune(db: Path, keep: int) -> int:
    """删掉旧 cookie，保留 creation_utc 最新的 keep 条。返回删除条数。"""
    with sqlite3.connect(db) as conn:
        cur = conn.execute(
            "DELETE FROM cookies "
            " WHERE host_key = ? AND name LIKE ? "
            "   AND name NOT IN ("
            "     SELECT name FROM cookies "
            "      WHERE host_key = ? AND name LIKE ? "
            "      ORDER BY creation_utc DESC LIMIT ?)",
            (COOKIE_HOST, COOKIE_PREFIX + "%",
             COOKIE_HOST, COOKIE_PREFIX + "%", keep),
        )
        deleted = cur.rowcount
        conn.commit()
    return deleted


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="dsh-cookie-clean",
        description="清理 DeepSeek Harness 堆积的 dsh-auth cookie（只留最新几条）",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="只报告条数与字节，不改任何东西")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                    help=f"保留最新几条 dsh-auth cookie（默认 {DEFAULT_KEEP}）")
    ap.add_argument("--db", default=None,
                    help="cookie 库路径（默认 Harness 用户数据目录里那份）")
    args = ap.parse_args()

    db = Path(args.db) if args.db else default_db()
    if not db.is_file():
        print(f"{FAIL} 找不到 {db}", file=sys.stderr)
        return 1

    rows = auth_cookies(db)
    count = len(rows)
    size = total_bytes(db)

    if count == 0:
        print(f"{OK} 没有 {COOKIE_PREFIX}* cookie，无需清理")
        return 0

    print(f"{INFO} {COOKIE_HOST} 下有 {count} 条 {COOKIE_PREFIX}* cookie"
          f"（约 {size} 字节）")
    if count <= args.keep:
        print(f"{OK} 数量正常（{count} 条 ≤ 保留 {args.keep} 条），无需清理")
        return 0

    # 崩溃线：Node 的 http.maxHeaderSize = 16384
    if size > 16384:
        print(f"{WARN} 已超过 Node 的 http.maxHeaderSize(16384)，"
              f"这正是启动失败的原因")

    if args.dry_run:
        print(f"{INFO} 将删除 {count - args.keep} 条，保留最新 {args.keep} 条")
        for name, created, _ in rows[:args.keep]:
            print(f"  ＋ {name}")
        print("  － 其余各条（见上）")
        print("\n(dry-run，未改动任何文件)")
        return 0

    if harness_running():
        print(f"{FAIL} {APP_NAME} 正在运行，Chromium 锁着数据库，"
              f"现在改会损坏它。", file=sys.stderr)
        print(f"{INFO} 请先退出 Harness 再跑一次。", file=sys.stderr)
        return 1

    # 先在临时文件上改并验证，通过后再原子替换原库；
    # 替换失败就把原文件挪回去，绝不留半成品。
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "Cookies"
        shutil.copy2(db, work)
        deleted = prune(work, args.keep)
        left = len(auth_cookies(work))
        left_bytes = total_bytes(work)
        if left > args.keep:
            print(f"{FAIL} 清理后仍有 {left} 条（预期 ≤ {args.keep}），已放弃，未改动原库",
                  file=sys.stderr)
            return 1

        # 原文件挪到临时目录（出错的唯一退路），写成功就随临时目录一起消失
        staged = Path(tmp) / "Cookies.orig"
        shutil.move(db, staged)
        try:
            # copy 而非 rename：保留原文件的 inode 与权限位
            shutil.copyfile(work, db)
        except OSError as e:
            shutil.move(staged, db)
            print(f"{FAIL} 写回失败，已还原原库：{e}", file=sys.stderr)
            return 1

    # 删掉可能残留的 journal，避免 Chromium 读到不一致状态
    journal = db.with_name(db.name + "-journal")
    if journal.exists():
        journal.unlink()

    print(f"{OK} 已清理：{count} → {left} 条（删除 {deleted} 条，"
          f"剩余约 {left_bytes} 字节）")
    print(f"{INFO} 现在可以打开 {APP_NAME} 了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
