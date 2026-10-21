"""从 Chromium 系浏览器（Edge/Chrome）导出 cookies 为 Netscape 格式。

默认导出 Edge 里 e-hentai / exhentai 的 cookie 到 gallery-dl 配置目录，
供 `gallery-dl` / `hentai_download.py` 使用。

用法: python src/export_cookies.py
      python src/export_cookies.py --browser chrome --out /tmp/cookies.txt

解密逻辑（v10 + AES-128-CBC，密钥来自钥匙串）由 `read_cookies` 暴露给其它脚本复用，
`exhentai_unblock.py` 就是靠它读登录状态的。
"""
import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
from hashlib import pbkdf2_hmac
from pathlib import Path

PREFIX_LEN = 32
SALT = b"saltysalt"

# 浏览器 → (cookie 库, 钥匙串条目)
BROWSERS = {
    "edge": (
        "~/Library/Application Support/Microsoft Edge/Default/Cookies",
        "Microsoft Edge Safe Storage",
    ),
    "chrome": (
        "~/Library/Application Support/Google/Chrome/Default/Cookies",
        "Chrome Safe Storage",
    ),
}

DEFAULT_OUT = "~/.config/gallery-dl/exh_cookies.txt"
DEFAULT_HOSTS = ("%e-hentai%", "%exhentai%")


def get_key(service: str = "Microsoft Edge Safe Storage") -> bytes:
    """取浏览器在钥匙串里的加密口令并派生出 AES-128 密钥。

    service 默认 Edge；Chrome 为 "Chrome Safe Storage"。
    """
    pw = subprocess.check_output(
        ["security", "find-generic-password", "-w", "-s", service],
        text=True,
    ).strip()
    return pbkdf2_hmac("sha1", pw.encode("utf-8"), SALT, 1003, dklen=16)


def aes_decrypt(key: bytes, data: bytes) -> str:
    """用 openssl 解一段 AES-128-CBC 密文（无填充），去掉 PKCS#7 与主机哈希前缀。"""
    iv = b" " * 16
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        fn = f.name
    try:
        out = subprocess.check_output(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-iv", iv.hex(),
             "-K", key.hex(), "-in", fn, "-nopad"],
            stderr=subprocess.DEVNULL,
        )
    finally:
        os.unlink(fn)
    if not out:
        return ""
    pad = out[-1]
    if not 1 <= pad <= 16 or pad > len(out):
        return ""
    out = out[:-pad]
    if len(out) >= PREFIX_LEN:
        out = out[PREFIX_LEN:]
    return out.decode("utf-8", "replace")


def read_cookies(
    browser: str = "edge",
    hosts: tuple[str, ...] = DEFAULT_HOSTS,
) -> list[dict]:
    """读出指定浏览器里匹配 hosts 的 cookie（明文）。

    返回 [{host, name, path, secure, value}]；解不开的条目被跳过。
    库文件先复制一份再读，避免浏览器占用锁库。
    """
    rel_db, service = BROWSERS[browser]
    db = Path(os.path.expanduser(rel_db))
    if not db.exists():
        return []
    key = get_key(service)

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "Cookies"
        copy.write_bytes(db.read_bytes())
        con = sqlite3.connect(copy)
        try:
            sql = "SELECT host_key, name, path, is_secure, encrypted_value FROM cookies"
            if hosts:
                sql += " WHERE " + " OR ".join("host_key LIKE ?" for _ in hosts)
                rows = con.execute(sql, hosts).fetchall()
            else:
                rows = con.execute(sql).fetchall()
        finally:
            con.close()

    out = []
    for host, name, path, secure, enc in rows:
        raw = bytes(enc)
        if raw[:3] == b"v10":
            try:
                val = aes_decrypt(key, raw[3:])
            except Exception:
                val = ""
        else:
            val = raw.decode("utf-8", "replace")
        if not val:
            continue
        out.append({
            "host": host,
            "name": name,
            "path": path,
            "secure": bool(secure),
            "value": val,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="导出浏览器 cookies 为 Netscape 格式")
    ap.add_argument("--browser", choices=sorted(BROWSERS), default="edge",
                    help="从哪个浏览器导出（默认 edge）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出文件路径")
    args = ap.parse_args()

    rows = read_cookies(args.browser)
    out_path = Path(os.path.expanduser(args.out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for c in rows:
            sec = "TRUE" if c["secure"] else "FALSE"
            f.write(f"{c['host']}\tTRUE\t{c['path']}\t{sec}\t0\t{c['name']}\t{c['value']}\n")
    print(f"wrote {len(rows)} candidate rows -> {out_path}")


if __name__ == "__main__":
    main()
