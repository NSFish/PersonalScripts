"""manga 脚本共用的小工具：图片扩展名判断、自然排序、零填充、中文数转阿拉伯。"""
import re
from pathlib import Path


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".avif")
_IMAGE_EXTS_SET = {ext.lower() for ext in IMAGE_EXTS}

# 漫画压缩包格式：.cbz 就是改了扩展名的 .zip，都用 zipfile 处理。
# .cbr/.rar 是 RAR 格式，需要额外工具，暂不支持。
ARCHIVE_EXTS = (".zip", ".cbz")
_ARCHIVE_EXTS_SET = {ext.lower() for ext in ARCHIVE_EXTS}

# 压缩时排除的隐藏文件（macOS 自带 .DS_Store 等）
EXCLUDE_HIDDEN_FILES = ('.DS_Store', '__MACOSX')

# 转换/整理类脚本的统一输出文件夹名：在输入路径的父目录下新建 result/，输出全放里面
OUTPUT_DIR_NAME = "result"

# primage 支持的输出格式（jpg 需映射为 jpeg）
VALID_OUTPUT_FORMATS = ('jpg', 'jpeg', 'png', 'webp', 'avif')


def normalize_primage_format(out_format: str) -> str:
    """把目标格式映射为 primage -f 接受的值（jpg/jpeg → jpeg）。"""
    fmt = out_format.lower()
    return "jpeg" if fmt in ("jpg", "jpeg") else fmt


def primage_quality(out_format: str) -> str:
    """各格式默认质量：avif 用 60（观感约等于 jpeg/webp 的 90，体积更小），其余用 90。"""
    return "60" if out_format.lower() == "avif" else "90"


def run_primage(input_path, output_path, out_format: str) -> None:
    """调用 primage 转换单张图片，失败抛 CalledProcessError，由调用方处理提示。"""
    import subprocess

    subprocess.run(
        [
            "primage", "-f", normalize_primage_format(out_format),
            "-q", primage_quality(out_format),
            "-o", str(output_path), str(input_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def is_archive_file(path) -> bool:
    """路径/文件名是否为受支持的漫画压缩包（.zip/.cbz）。"""
    return Path(path).suffix.lower() in _ARCHIVE_EXTS_SET


def copy_mac_tags(src, dst) -> None:
    """把源文件的 macOS 标签复制到目标文件；无标签或失败只打印提示，不抛异常。"""
    try:
        tags = get_mac_tags(str(src))
    except Exception:
        return
    if not tags:
        return
    try:
        if set_mac_tags(str(dst), tags):
            print(f"🏷️ 已复制标签: {tags}")
        else:
            print(f"⚠️ 标签写入失败: {dst}")
    except Exception as e:
        print(f"⚠️ 标签写入失败: {dst} ({e})")


def is_image_file(path) -> bool:
    """路径/文件名是否为受支持的图片格式（按扩展名判断）。"""
    return Path(path).suffix.lower() in _IMAGE_EXTS_SET


def natural_key(s: str):
    """自然排序 key：数字段按数值比较，如 2 < 10。"""
    # isdecimal 而非 isdigit：int() 不接受上标数字等 isdigit 为真的字符
    return [int(t) if t.isdecimal() else t.lower() for t in re.split(r"(\d+)", str(s))]


def pad(n: int, width: int) -> str:
    """把整数 n 零填充到 width 位。"""
    return str(n).zfill(width)


def cn_to_arab(cn: str):
    """中文/阿拉伯数字字符串转 int；无法识别返回 None。"""
    if cn.isdecimal():
        return int(cn)
    import cn2an

    try:
        return cn2an.cn2an(cn, "normal")
    except Exception:
        return None


def get_mac_tags(path) -> list:
    """读取文件的 macOS 标签（Finder colors/tags）。非 macOS 或读取失败返回空列表。"""
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(path))
    values, _ = url.resourceValuesForKeys_error_(["NSURLTagNamesKey"], None)
    if values is None:
        return []
    return list(values.get("NSURLTagNamesKey") or [])


def set_mac_tags(path, tags) -> bool:
    """写入文件的 macOS 标签，返回是否成功。pyobjc 会把 NSError** 出参折成 (ok, error) 元组。"""
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(path))
    ok, _error = url.setResourceValue_forKey_error_(
        list(tags) if tags else [], "NSURLTagNamesKey", None
    )
    return bool(ok)
