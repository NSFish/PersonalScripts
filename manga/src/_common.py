"""manga 脚本共用的小工具：图片扩展名判断、自然排序、零填充、中文数转阿拉伯。"""
import re
from pathlib import Path


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".avif")
_IMAGE_EXTS_SET = {ext.lower() for ext in IMAGE_EXTS}


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
