#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 Violentmonkey (Edge) 的 NGA 摸鱼脚本黑名单中删除指定用户。

用法: python nga_blacklist_remove.py <用户名或uid> [--dry-run]
需要先关闭 Edge。
"""

import json
import os
import sys

# 优先使用装有 leveldb 绑定的 venv（PersonalScripts 项目 venv 未装这些依赖）
def _ensure_venv():
    try:
        import rleveldb  # noqa
        import leveldb  # noqa (amulet-leveldb)
        return
    except ImportError:
        pass
    candidates = [
        os.path.expanduser("~/Documents/Playground/tools/.venv/bin/python"),
    ]
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, ".venv", "bin", "python"))
    for vpy in candidates:
        if os.path.exists(vpy) and os.path.abspath(sys.executable) != os.path.abspath(vpy):
            os.execv(vpy, [vpy] + sys.argv)


_ensure_venv()

import rleveldb  # noqa: E402
import leveldb  # noqa: E402 (amulet-leveldb)

DB_PATH = os.path.expanduser(
    "~/Library/Application Support/Microsoft Edge/Default/Local Extension Settings/eeagobfjdenkkddmbclomhiblgggliao"
)
KEY = "val:8"
BAN_KEY = "hld__NGA_ban_list"


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    target = next((a for a in args if not a.startswith("--")), None)
    if not target:
        print("用法: python nga_blacklist_remove.py <用户名或uid> [--dry-run]", file=sys.stderr)
        sys.exit(1)

    # 读取：plyvel 无法解压 Edge 的块，改用 rleveldb 读原始记录
    rdb = rleveldb.RawLevelDb(DB_PATH)
    try:
        recs = rdb.iterate_records_raw()
    except Exception as e:
        rdb.close()
        print("读取 LevelDB 失败:", e, file=sys.stderr)
        sys.exit(1)

    matches = [
        r for r in recs
        if getattr(r, "user_key", r.key[:-8] if len(r.key) >= 8 else r.key) == b"val:8"
        and r.state == rleveldb.KeyState.Live
    ]
    if not matches:
        rdb.close()
        print("未找到 key", KEY, file=sys.stderr)
        sys.exit(1)
    rec = max(matches, key=lambda r: r.seq)
    try:
        obj = json.loads(rec.value.decode("utf-8"))
    except Exception as e:
        rdb.close()
        print("解析 JSON 失败:", e, file=sys.stderr)
        sys.exit(1)
    rdb.close()

    if BAN_KEY not in obj:
        print("未找到黑名单字段", BAN_KEY, file=sys.stderr)
        sys.exit(1)

    # Violentmonkey 值编码：类型前缀 + JSON，"s" 表示字符串
    encoded = obj[BAN_KEY]
    if not encoded or encoded[0] != "s":
        print("意外的值类型前缀:", encoded[:1] if encoded else None, file=sys.stderr)
        sys.exit(1)
    arr = json.loads(encoded[1:])
    print("黑名单总人数:", len(arr))

    removed = [u for u in arr if u.get("name") == target or u.get("uid") == target]
    kept = [u for u in arr if u.get("name") != target and u.get("uid") != target]

    if not removed:
        print("未找到匹配用户:", target)
        sys.exit(0)
    print("将删除:", ", ".join(f"{u.get('name')} (uid:{u.get('uid')})" for u in removed))

    if dry_run:
        print("[dry-run] 不写入。")
        sys.exit(0)

    obj[BAN_KEY] = "s" + json.dumps(kept, ensure_ascii=False, separators=(",", ":"))
    new_raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    # 写入：amulet-leveldb（Mojang LevelDB，Edge 使用的实现）
    db = leveldb.LevelDB(DB_PATH)
    try:
        db.put(b"val:8", new_raw)
    finally:
        db.close()
    print(f"删除完成: {len(arr)} -> {len(kept)}")


if __name__ == "__main__":
    main()
