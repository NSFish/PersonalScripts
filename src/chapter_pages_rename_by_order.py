#!/usr/bin/env python3
"""递归把每个子目录（含目标自身）里的文件按排序重命名为零填充序号。

既支持文件夹，也支持单个 .zip / .cbz：压缩包原地重写（包名不变、
macOS 标签写回），包内文件编号规则与文件夹内单个目录一致。
压缩包只支持两种结构：拍平（文件全在根目录）或单顶层文件夹；
多文件夹/混放直接报错退出。
替代原 chapter_pages_rename_by_order.sh：纯 pathlib 逻辑，跨平台。
支持 -n/--dry-run 预览、-v/--verbose。
"""
import argparse
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

from _common import (
    copy_mac_tags,
    extract_zip,
    fix_zip_filename,
    get_mac_tags,
    is_archive_file,
    is_hidden_part,
    natural_key,
    pad,
)

TMP_PREFIX = "__rename_tmp_"


def plan_names(files: list[Path]) -> list[tuple[Path, str]]:
    """给排序后的文件列表规划零填充序号新名，返回 [(原路径, 新名)]。

    序号从 0 起始，位宽 max(2, len(str(总数)))，保留原扩展名；
    已经是规范名的文件不进 plan（保持幂等、汇总数字真实）。
    被 ebook_2_zip 等脚本复用：命名规则只有这一处定义。
    """
    n = len(files)
    if n == 0:
        return []
    digit = max(2, len(str(n)))
    plan = []
    for i, f in enumerate(files):
        new_name = f"{pad(i, digit)}{f.suffix}"
        if new_name != f.name:
            plan.append((f, new_name))
    return plan


def process_directory(d: Path, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """处理单个目录，返回 (成功重命名数, 失败数)。压缩包本身跳过，留给包流程处理。"""
    if verbose:
        print(f"🛠 正在处理文件夹: {d}")

    files = sorted(
        (
            f
            for f in d.iterdir()
            if f.is_file() and not f.name.startswith(".") and not is_archive_file(f)
        ),
        key=lambda f: natural_key(f.name),
    )
    n = len(files)
    if n == 0:
        if verbose:
            print("  目录为空，跳过处理")
        return 0, 0

    plan = plan_names(files)

    if not plan:
        if verbose:
            print("  文件名已规范，无需处理")
        return 0, 0

    if dry_run:
        for f, new_name in plan:
            print(f'  ✅  "{f.name}" -> "{new_name}"')
        return len(plan), 0

    # 两步重命名：先搬到唯一临时名，再搬到目标名，避免序号交叉覆盖。
    token = uuid.uuid4().hex[:8]
    tmps = []
    failed = 0
    for i, (f, new_name) in enumerate(plan):
        tmp = f.with_name(f"{TMP_PREFIX}{token}_{i}__{f.suffix}")
        while tmp.exists():  # 极端情况下撞名，换一个 token
            token = uuid.uuid4().hex[:8]
            tmp = f.with_name(f"{TMP_PREFIX}{token}_{i}__{f.suffix}")
        try:
            f.rename(tmp)
        except OSError as e:
            print(f'❌  "{f.name}" 重命名失败: {e}')
            failed += 1
            continue
        tmps.append((f.name, tmp, new_name))

    renamed = 0
    for orig_name, tmp, new_name in tmps:
        try:
            tmp.rename(tmp.with_name(new_name))
        except OSError as e:
            print(f'❌  "{orig_name}" -> "{new_name}" 失败: {e}')
            failed += 1
            continue
        print(f'✅  "{orig_name}" -> "{new_name}"')
        renamed += 1

    leftovers = sorted(p.name for p in d.iterdir() if p.name.startswith(TMP_PREFIX))
    if leftovers:
        print(f"⚠️  目录仍有残留临时文件: {d} -> {leftovers}")

    return renamed, failed


def resolve_archive_content(archive: Path) -> Path:
    """判定包内待编号的目录（相对于包根）：拍平返回 Path(".")，单顶层文件夹返回其名。

    多顶层文件夹、根目录与子文件夹混放、两层以上嵌套直接抛 RuntimeError。
    隐藏文件（.DS_Store / __MACOSX / 点文件）不参与判定。读包失败抛异常。
    """
    root_files = 0
    tops: dict[str, str] = {}  # 顶层名 -> 首个目击条目名（报错用）
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            fixed = fix_zip_filename(info)
            if not fixed:
                continue
            rel = Path(fixed)
            if rel.is_absolute() or ".." in rel.parts:
                continue
            if any(is_hidden_part(part) for part in rel.parts):
                continue
            if info.is_dir():
                inner = Path(fixed.rstrip("/"))
                if len(inner.parts) != 1:
                    raise RuntimeError(
                        f'"{archive.name}" 内含多层文件夹，不支持处理，已停止: {fixed}'
                    )
                tops.setdefault(inner.parts[0], fixed)
                continue
            if len(rel.parts) == 1:
                root_files += 1
            elif len(rel.parts) == 2:
                tops.setdefault(rel.parts[0], fixed)
            else:
                raise RuntimeError(
                    f'"{archive.name}" 内含多层文件夹，不支持处理，已停止: {fixed}'
                )
    if not tops:
        return Path(".")
    if root_files == 0 and len(tops) == 1:
        return Path(next(iter(tops)))
    offender = next(iter(tops.values()))
    raise RuntimeError(f'"{archive.name}" 内含子文件夹，不支持处理，已停止: {offender}')


def rezip_preserving(extract_dir: Path, stage_path: Path) -> None:
    """把解压目录按相对路径原样压回 stage_path（保留文件夹结构与隐藏文件）。"""
    files = [p for p in extract_dir.rglob("*") if p.is_file()]
    files.sort(key=lambda p: natural_key(str(p.relative_to(extract_dir).as_posix())))
    with zipfile.ZipFile(stage_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(extract_dir))


def process_archive(archive: Path, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """原地重命名单个 .zip/.cbz 包内文件，包名与标签不变。返回 (重命名数, 失败数)。"""
    print(f"📦 正在处理压缩包: {archive}")
    try:
        tags = get_mac_tags(str(archive))
    except Exception:
        tags = []
    if verbose:
        print(f"  标签: {', '.join(tags) if tags else '(无)'}")

    with tempfile.TemporaryDirectory() as tmp:
        extract_dir = Path(tmp) / "unpacked"
        extract_dir.mkdir()
        try:
            extract_zip(archive, extract_dir)
        except Exception as e:
            print(f'❌  "{archive.name}" 解压失败: {e}')
            return 0, 1

        # 解压后二次确认结构（与预检同一规则），违规直接抛给调用方终止全流程。
        items = [p for p in extract_dir.iterdir() if not is_hidden_part(p.name)]
        inner_dirs = [p for p in items if p.is_dir()]
        root_files = [p for p in items if p.is_file()]
        if len(inner_dirs) > 1 or (inner_dirs and root_files):
            raise RuntimeError(
                f'"{archive.name}" 内含子文件夹，不支持处理，已停止: {inner_dirs[0].name}/'
            )
        if inner_dirs:
            content_dir = inner_dirs[0]
            if verbose:
                print(f"  包内目录: {content_dir.name}/")
            if any(
                p for p in content_dir.rglob("*") if p.is_dir() and not is_hidden_part(p.name)
            ):
                raise RuntimeError(
                    f'"{archive.name}" 内含多层文件夹，不支持处理，已停止: {content_dir.name}/'
                )
        else:
            content_dir = extract_dir

        renamed, failed = process_directory(content_dir, dry_run, verbose)

        if dry_run or renamed == 0:
            if renamed == 0 and failed == 0 and verbose:
                print("  文件名已规范，无需处理")
            return renamed, failed

        # 先写临时包再原子替换，中途失败不毁原包；扩展名沿用原包。
        stage_path = archive.with_name(f"{archive.stem}.tmp{archive.suffix}")
        if stage_path.exists():
            stage_path.unlink()
        try:
            rezip_preserving(extract_dir, stage_path)
            if tags:
                copy_mac_tags(str(archive), str(stage_path))
            stage_path.replace(archive)
        except OSError as e:
            print(f'❌  "{archive.name}" 回写失败: {e}')
            return 0, failed + 1
        finally:
            if stage_path.exists():
                stage_path.unlink()

    print(f"✅ 已更新压缩包: {archive.name}（{renamed} 个文件）")
    return renamed, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="按数字排序重命名目录/压缩包内的文件")
    parser.add_argument("-n", "--dry-run", action="store_true", help="预览模式(不实际重命名)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细处理过程")
    parser.add_argument("target", help="目标目录或 .zip/.cbz 压缩包")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if args.dry_run:
        print("🏃 运行模式: 预览 (dry-run)")
    else:
        print("🏃 运行模式: 实际执行")

    archives: list[Path] = []
    dirs: list[Path] = []
    if target.is_file() and is_archive_file(target):
        archives = [target]
    elif target.is_dir():
        if args.verbose:
            print(f"🔍 扫描目录: {target}")
        # 目标目录自身也要处理（旧 shell 版语义），再递归子目录。
        dirs = [target]
        dirs.extend(sorted(p for p in target.rglob("*") if p.is_dir()))
        archives = sorted(
            (
                p
                for p in target.rglob("*")
                if p.is_file() and is_archive_file(p) and not p.stem.endswith(".tmp")
            ),
            key=lambda p: natural_key(str(p.relative_to(target).as_posix())),
        )
    else:
        print(f"错误：请指定正确的目标目录或 .zip/.cbz 压缩包: {args.target}")
        sys.exit(1)

    # 只支持拍平或单顶层文件夹：先全部校验，违规直接退出，不做任何改动。
    for archive in archives:
        try:
            resolve_archive_content(archive)
        except RuntimeError as e:
            print(f"❌ {e}")
            sys.exit(1)
        except Exception as e:
            print(f'❌ "{archive.name}" 读取失败，已停止: {e}')
            sys.exit(1)

    dirs_done = 0
    renamed = 0
    failed = 0
    for d in dirs:
        got, bad = process_directory(d, args.dry_run, args.verbose)
        failed += bad
        if got:
            dirs_done += 1
            renamed += got

    archives_done = 0
    for archive in archives:
        try:
            got, bad = process_archive(archive, args.dry_run, args.verbose)
        except RuntimeError as e:
            print(f"❌ {e}")
            failed += 1
            break
        except Exception as e:
            print(f"❌ {archive.name} 处理失败: {e}")
            failed += 1
            continue
        failed += bad
        if got:
            archives_done += 1
            renamed += got

    if args.dry_run:
        print(f"\n共扫描 {len(dirs)} 个文件夹、{len(archives)} 个压缩包，待重命名 {renamed} 个文件")
    else:
        print(f"\n共处理 {dirs_done} 个文件夹、{archives_done} 个压缩包，重命名 {renamed} 个文件")
    if failed:
        print(f"❌ {failed} 个文件处理失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
