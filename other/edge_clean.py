#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edge_clean.py — 清理 Microsoft Edge 在本地堆积的更新备份与组件缓存（零依赖，仅标准库）。

清理对象（只删旧版本/缓存，不碰当前版本与用户数据）：
  EdgeUpdater/apps/msedge-stable/  仅保留与 /Applications 下 Edge 同名的版本目录
  EdgeUpdater/apps/msedge-updater/ 仅保留 Current 软链指向的版本目录
  Microsoft Edge/component_crx_cache/ 全部清空（重启 Edge 自动重下）
  EdgeUpdater/updater.log.old、updater_history.jsonl.old

用法：
  python3 other/edge_clean.py              # 要求先退出 Edge，直接清理
  python3 other/edge_clean.py --dry-run    # 只列出将删除项与可释放空间
  python3 other/edge_clean.py --force      # Edge 运行中也照常清理（不推荐）
"""
import argparse
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

EDGE_APP = Path("/Applications/Microsoft Edge.app")
EUPD = Path.home() / "Library/Application Support/Microsoft/EdgeUpdater"
STABLE = EUPD / "apps/msedge-stable"
UPDATER = EUPD / "apps/msedge-updater"
CACHE = Path.home() / "Library/Application Support/Microsoft Edge/component_crx_cache"
OLD_LOGS = [EUPD / "updater.log.old", EUPD / "updater_history.jsonl.old"]


def edge_version() -> str:
    """读 /Applications 下 Edge 的版本号，读不到返回空串。"""
    try:
        with (EDGE_APP / "Contents/Info.plist").open("rb") as f:
            return str(plistlib.load(f).get("CFBundleShortVersionString", "") or "")
    except (OSError, ValueError):
        return ""


def edge_running() -> bool:
    try:
        r = subprocess.run(["pgrep", "-x", "Microsoft Edge"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except OSError:
        return False


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def collect() -> tuple[list[Path], str, str]:
    """返回 (待删路径列表, Edge版本号, updater版本号)。版本号为空串表示取不到。"""
    cur = edge_version()
    ucur = ""
    try:
        ucur = (EUPD / "Current").readlink().name
    except OSError:
        pass
    victims: list[Path] = []
    if cur and STABLE.is_dir():
        victims += [p for p in STABLE.iterdir() if p.name != cur]
    if ucur and UPDATER.is_dir():
        victims += [p for p in UPDATER.iterdir() if p.name != ucur]
    if CACHE.is_dir():
        victims += list(CACHE.iterdir())
    victims += [p for p in OLD_LOGS if p.exists()]
    return victims, cur, ucur


def remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="清理 Edge 本地更新备份与组件缓存",
                                 prog="edge-clean")
    ap.add_argument("--dry-run", action="store_true", help="只列出将删除项，不删除")
    ap.add_argument("--force", action="store_true", help="Edge 运行中也照常清理")
    args = ap.parse_args(argv)

    victims, cur, ucur = collect()
    if not cur:
        print("❌ 读不到 Edge 版本号（/Applications 下无 Edge？），不做删除", file=sys.stderr)
        return 1
    if edge_running() and not args.dry_run and not args.force:
        print("❌ Edge 正在运行，先退出再清（或加 --force）", file=sys.stderr)
        return 1
    if not victims:
        print(f"✅ 没什么可清的（保留 Edge {cur} / updater {ucur or '未知'}）")
        return 0

    freed = sum(dir_size(p) for p in victims)
    if args.dry_run:
        print(f"将删除 {len(victims)} 项，约 {freed // 1024 // 1024} MB：")
        for p in victims:
            print(f"  － {p}（约 {dir_size(p) // 1024 // 1024} MB）")
        print(f"保留 Edge {cur} / updater {ucur or '未知'}")
        return 0

    freed = 0
    for p in victims:
        try:
            size = dir_size(p)
            remove(p)
            freed += size
        except OSError as e:
            print(f"⚠️ 删失败 {p}：{e}", file=sys.stderr)
    print(f"✅ 释放约 {freed // 1024 // 1024} MB，保留 Edge {cur} / updater {ucur or '未知'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
