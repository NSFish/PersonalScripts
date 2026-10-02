#!/usr/bin/env python3
"""按元数据重命名已下载的本子目录（无需重新下载）。

用法: python hentai_rename.py <目录> [目录 ...]

每个目录可以是单本子或父目录：
- 自身有 metadata .json（gallery-dl --write-info-json 或 comic-looms 写的）→ 用它重命名；
- 没有 json 但有子目录 → 当父目录，子目录逐个重命名；
- 否则 → 当无元数据单本，按目录现名走同一套规范化（去标签、拆作者）。

命名规则与 hentai_download 共用同一套逻辑（build_name）：
[罗马音作者] 罗马音标题 | 中文标题（无中文则日文，都无则省略）。
不是目录的目标会被报错；有报错目标时 exit 1，否则 exit 0。
"""
import argparse
import sys
from pathlib import Path

from hentai_download import rename_one


def _has_metadata(d: Path) -> bool:
    try:
        return any(p.suffix == ".json" and p.is_file() for p in d.iterdir())
    except OSError:
        return False


def rename_target(target: Path) -> int:
    """重命名 target（单本子或父目录）；返回处理过的本子数（目录目标恒 ≥1，现名无变化也算处理过）。"""
    if _has_metadata(target):
        rename_one(target)
        return 1
    children = sorted(c for c in target.iterdir() if c.is_dir())
    if children:
        for child in children:
            rename_one(child)
        return len(children)
    rename_one(target)  # 无 json 单本：按现名规范化
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="按元数据重命名已下载的本子目录（共用 hentai_download 的命名逻辑）")
    parser.add_argument("dirs", nargs="+", help="本子目录或其父目录（可多个）")
    args = parser.parse_args(argv)
    failed = 0
    for raw in args.dirs:
        target = Path(raw)
        if not target.is_dir():
            print(f"❌ 不是目录: {raw}")
            failed += 1
            continue
        rename_target(target)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
