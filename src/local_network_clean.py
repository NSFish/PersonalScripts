#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
local_network_clean.py — 清理 macOS「隐私与安全性 > 本地网络」里堆积的残留条目
（零依赖，仅标准库）。

调研结论（macOS 26.x 实测）
----------------------------
1. 「本地网络」权限**不在 TCC 里**。`tccutil reset LocalNetwork` 会被 tccd 拒掉：
       "Invalid Service Name: kTCCServiceLocalNetwork (Service name is invalid on
        this platform)"
   tccd 的服务名清单里根本没有 local network 这一项，所以系统设置里没法一键重置。

2. 它实际由 NetworkExtension 的一份 "network privacy" 配置托管，存放在
       /Library/Preferences/com.apple.networkextension.plist
   （NSKeyedArchiver 归档）。顶层 key 是配置 UUID，其中名称以
   `com.apple.preferences.networkprivacy-` 开头的那个就是「本地网络」；
   它的 PathController → Rules 里每一项是一条 NEPathRule，用
   **App 可执行文件的绝对路径**（Path 字段）索引。

3. 为什么条目会越攒越多：
   App 自动更新后签名变了，macOS 会在
       /private/var/folders/<xx>/<hash>/X/<bundleid>.code_sign_clone/code_sign_clone.XXXXXX/
   复制一份改过签名的副本，并给这个副本**新增**一条规则，旧规则从不回收；
   App 被卸载后规则同样留下。于是列表里出现几十条同名条目，图标还是灰色占位图。

4. 改写该文件后无需重启：nehelper 用 FSEvents 监听它（LaunchDaemons 里的
   com.apple.nehelper.plist），文件一变就自动重载。

清理规则
--------
  - Path 指向 code_sign_clone 副本 → 删（副本只是临时签名产物）
  - Path 指向的 App 已不存在（卸载/移动）→ 删
  - 其余（真实 App、系统默认规则）→ 保留
写回前自动备份原文件。

用法
----
  local-network-clean --dry-run            # 只看会删哪些，不改任何东西
  local-network-clean                      # 需要 root；非 root 时会弹系统授权框
  local-network-clean --keep-clone         # 保留 code_sign_clone 副本的规则
  local-network-clean --prune-clone-dirs   # 顺带删掉没人运行的副本目录（省磁盘）
  local-network-clean --plist 路径         # 指向别的 plist（测试用）
"""
import argparse
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_PLIST = Path("/Library/Preferences/com.apple.networkextension.plist")
PRIVACY_PREFIX = "com.apple.preferences.networkprivacy"
CLONE_MARK = "/code_sign_clone"
# code_sign_clone 副本所在的临时根：/private/var/folders/<2位>/<hash>/X/
CLONE_ROOT = Path("/var/folders")


# --------------------------------------------------------------------- 解析归档

def load_plist(path: Path) -> dict:
    with path.open("rb") as f:
        return plistlib.load(f)


def _ref(objs: list, value):
    """把归档里的 UID 引用解成对象；非引用原样返回。"""
    if isinstance(value, plistlib.UID):
        return objs[value]
    return value


def find_privacy_config(plist: dict, objs: list):
    """找出「本地网络」那份 NEConfiguration，返回 (顶层 key, 配置字典)；找不到返回 (None, None)。"""
    for key, value in plist.get("$top", {}).items():
        if not isinstance(value, plistlib.UID):
            continue
        conf = objs[value]
        if not isinstance(conf, dict):
            continue
        name = _ref(objs, conf.get("Name"))
        if isinstance(name, str) and name.startswith(PRIVACY_PREFIX):
            return key, conf
    return None, None


def rules_array(plist: dict, objs: list):
    """取出「本地网络」配置的规则数组（NSArray 字典）；找不到返回 None。"""
    _, conf = find_privacy_config(plist, objs)
    if conf is None:
        return None
    controller = _ref(objs, conf.get("PathController"))
    rules = _ref(objs, controller.get("Rules")) if isinstance(controller, dict) else None
    return rules if isinstance(rules, dict) and isinstance(rules.get("NS.objects"), list) else None


def rule_paths(plist: dict, objs: list):
    """列出规则数组里每条规则对应的 App 路径（没有路径的记为 None）。"""
    rules = rules_array(plist, objs)
    if rules is None:
        return None, None
    items = rules["NS.objects"]
    paths = []
    for item in items:
        rule = _ref(objs, item)
        path = _ref(objs, rule.get("Path")) if isinstance(rule, dict) else None
        if isinstance(path, str) and path != "$null":
            paths.append(path)
        else:
            paths.append(None)
    return items, paths


def classify(path: str | None, keep_clone: bool) -> str:
    """给一条规则定性：'clone'（签名副本）/ 'missing'（App 已不在）/ 'keep'。"""
    if path is None:
        return "keep"
    if not keep_clone and CLONE_MARK in path:
        return "clone"
    if not os.path.exists(path):
        return "missing"
    return "keep"


# --------------------------------------------------------------------- 写回

def write_plist(path: Path, plist: dict) -> None:
    """原子写回：先写同目录临时文件再 rename，权限/属主跟原文件一致。"""
    stat = path.stat()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".com.apple.networkextension.")
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            plistlib.dump(plist, f, fmt=plistlib.FMT_BINARY)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, stat.st_mode & 0o7777)
        os.chown(tmp, stat.st_uid, stat.st_gid)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".bak." + time.strftime("%Y%m%d-%H%M%S"))


# --------------------------------------------------------------------- 副本目录

def running_commands() -> str:
    """当前所有进程的命令行拼串，用来判断副本目录是否还在被使用。"""
    try:
        r = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True)
        return r.stdout
    except OSError:
        return ""


def dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def find_clone_dirs() -> list[Path]:
    """找出所有 code_sign_clone 副本目录。"""
    if not CLONE_ROOT.is_dir():
        return []
    return sorted(CLONE_ROOT.glob("*/*/X/*.code_sign_clone"))


def prune_clone_dirs(apply: bool) -> int:
    """删掉没人运行的 code_sign_clone 副本目录，返回释放的字节数。"""
    cmds = running_commands()
    freed = 0
    for d in find_clone_dirs():
        if str(d) in cmds:
            print(f"  ⏭️  {d}（正在被使用，跳过）")
            continue
        size = dir_size(d)
        if apply:
            try:
                shutil.rmtree(d)
            except OSError as e:
                print(f"  ⚠️  删失败 {d}：{e}", file=sys.stderr)
                continue
        freed += size
        print(f"  － {d}（约 {size // 1024 // 1024} MB）")
    return freed


# --------------------------------------------------------------------- 提权

def escalation_command(argv: list[str]) -> str:
    """拼出「以 root 重跑本脚本」的 AppleScript 命令。"""
    script = str(Path(sys.argv[0]).resolve())
    cmd = " ".join([shlex.quote(sys.executable), shlex.quote(script), *map(shlex.quote, argv)])
    # AppleScript 字符串里反斜杠和双引号都要转义
    cmd = cmd.replace("\\", "\\\\").replace('"', '\\"')
    return f'do shell script "{cmd}" with administrator privileges'


def escalate(argv: list[str]) -> int:
    """非 root 时用系统授权框重新以 root 跑一遍。"""
    try:
        r = subprocess.run(["osascript", "-e", escalation_command(argv)],
                           capture_output=True, text=True)
    except OSError as e:
        print(f"❌ 弹授权框失败：{e}", file=sys.stderr)
        return 1
    if r.stdout:
        print(r.stdout, end="")
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
    return r.returncode


def tcc_has_local_network() -> bool:
    """旧版 macOS（14/15）把本地网络放在 TCC 里，这里探一下以便给出对应建议。"""
    db = Path.home() / "Library/Application Support/com.apple.TCC/TCC.db"
    if not db.exists():
        return False
    try:
        r = subprocess.run(
            ["sqlite3", str(db),
             "select count(*) from access where service='kTCCServiceLocalNetwork';"],
            capture_output=True, text=True)
        return r.returncode == 0 and r.stdout.strip() not in ("", "0")
    except OSError:
        return False


# --------------------------------------------------------------------- 主流程

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(
        description="清理 macOS「本地网络」隐私列表里的残留条目",
        prog="local-network-clean")
    ap.add_argument("--dry-run", action="store_true", help="只列出将删除的条目，不改文件")
    ap.add_argument("--plist", default=str(DEFAULT_PLIST), help="目标 plist（默认系统那份）")
    ap.add_argument("--keep-clone", action="store_true", help="保留 code_sign_clone 副本的规则")
    ap.add_argument("--prune-clone-dirs", action="store_true", help="顺带删除没人运行的副本目录")
    ap.add_argument("--no-escalate", action="store_true", help="不弹系统授权框（请自行 sudo）")
    args = ap.parse_args(argv)

    plist_path = Path(args.plist)
    is_system = plist_path == DEFAULT_PLIST

    if not plist_path.exists():
        print(f"❌ 找不到 {plist_path}", file=sys.stderr)
        if tcc_has_local_network():
            print("💡 你的系统把「本地网络」存在 TCC 里（旧版 macOS），"
                  "用 `sudo tccutil reset LocalNetwork` 重置。", file=sys.stderr)
        return 1

    plist = load_plist(plist_path)
    objs = plist["$objects"]
    items, paths = rule_paths(plist, objs)
    if items is None:
        print(f"❌ {plist_path} 里没有「本地网络」配置（名称以 {PRIVACY_PREFIX} 开头）", file=sys.stderr)
        if tcc_has_local_network():
            print("💡 你的系统把「本地网络」存在 TCC 里（旧版 macOS），"
                  "用 `sudo tccutil reset LocalNetwork` 重置。", file=sys.stderr)
        return 1

    verdicts = [classify(p, args.keep_clone) for p in paths]
    stale = [(i, p) for i, p, v in zip(items, paths, verdicts) if v != "keep"]

    # 改系统那份需要 root；读不读都要先看看有没有得清，免得白弹授权框
    if is_system and stale and not args.dry_run and os.geteuid() != 0:
        if args.no_escalate:
            print("❌ 需要 root，请用 sudo 运行（或去掉 --no-escalate 自动弹授权框）", file=sys.stderr)
            return 1
        print(f"💡 待清理 {len(stale)} 条，需要管理员权限，正在请求授权…")
        return escalate(argv)

    print(f"💡 存储位置：{plist_path}（NetworkExtension 的 network privacy 配置）")
    print(f"规则总数 {len(items)} 条，其中待清理 {len(stale)} 条")
    for i, p in stale:
        tag = "签名副本" if "/code_sign_clone" in p else "App 已不存在"
        print(f"  － {p}  [{tag}]")
    for p in (p for p, v in zip(paths, verdicts) if v == "keep" and p):
        print(f"  ＋ {p}")

    if args.dry_run:
        print("\n(dry-run，未改动任何文件)")
    elif not stale:
        print("\n✅ 没什么可清的")
    else:
        bak = backup_path(plist_path)
        shutil.copy2(plist_path, bak)
        rules = rules_array(plist, objs)
        rules["NS.objects"] = [i for i in items if i not in {s[0] for s in stale}]
        write_plist(plist_path, plist)
        print(f"\n✅ 已清理 {len(stale)} 条，备份在 {bak}")
        print("   nehelper 会自动重载；如列表没变，重启「系统设置」再看。")

    if args.prune_clone_dirs:
        print("\n清理没人运行的 code_sign_clone 副本目录：")
        freed = prune_clone_dirs(apply=not args.dry_run)
        if freed:
            print(f"{'已释放' if not args.dry_run else '可释放'}约 {freed // 1024 // 1024} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
