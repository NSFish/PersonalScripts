"""manga 脚本共用的小工具：图片扩展名判断、自然排序、零填充、中文数转阿拉伯。"""
import re


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".avif")
_IMAGE_EXTS_SET = {ext.lower() for ext in IMAGE_EXTS}


def is_image_file(path) -> bool:
    """路径/文件名是否为受支持的图片格式（按扩展名判断）。"""
    from pathlib import Path

    return Path(path).suffix.lower() in _IMAGE_EXTS_SET


def natural_key(s: str):
    """自然排序 key：数字段按数值比较，如 2 < 10。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def pad(n: int, width: int) -> str:
    """把整数 n 零填充到 width 位。"""
    return str(n).zfill(width)


def cn_to_arab(cn: str):
    """中文/阿拉伯数字字符串转 int；无法识别返回 None。"""
    if cn.isdigit():
        return int(cn)
    import cn2an

    try:
        return cn2an.cn2an(cn, "normal")
    except Exception:
        return None
