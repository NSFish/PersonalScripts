import os, sqlite3, subprocess, tempfile
from hashlib import pbkdf2_hmac

EDGE_COOKIES = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/Cookies")
OUT = os.path.expanduser("~/.config/gallery-dl/exh_cookies.txt")
PREFIX_LEN = 32

def get_key():
    pw = subprocess.check_output(
        ["security", "find-generic-password", "-w", "-s", "Microsoft Edge Safe Storage"],
        text=True
    ).strip()
    return pbkdf2_hmac("sha1", pw.encode("utf-8"), b"saltysalt", 1003, dklen=16)

def aes_decrypt(key, data):
    iv = b" " * 16
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data); fn = f.name
    try:
        out = subprocess.check_output(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-iv", iv.hex(),
             "-K", key.hex(), "-in", fn, "-nopad"],
            stderr=subprocess.DEVNULL
        )
    finally:
        os.unlink(fn)
    pad = out[-1]
    out = out[:-pad]
    if len(out) >= PREFIX_LEN:
        out = out[PREFIX_LEN:]
    return out.decode("utf-8", "replace")

def main():
    key = get_key()
    # copy DB to avoid lock
    tmp = "/tmp/edge_cookies_export.db"
    subprocess.run(["cp", EDGE_COOKIES, tmp], check=True)
    con = sqlite3.connect(tmp)
    rows = con.execute(
        "SELECT host_key, name, path, is_secure, encrypted_value FROM cookies "
        "WHERE host_key LIKE '%e-hentai%' OR host_key LIKE '%exhentai%'"
    ).fetchall()
    with open(OUT, "w") as f:
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
            sec = "TRUE" if secure else "FALSE"
            f.write(f"{host}\tTRUE\t{path}\t{sec}\t0\t{name}\t{val}\n")
    print(f"wrote {len(rows)} candidate rows -> {OUT}")

if __name__ == "__main__":
    main()
