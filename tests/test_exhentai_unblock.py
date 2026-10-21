"""exhentai_unblock / export_cookies 的回归测试。

覆盖不依赖真实网络与真实浏览器的那部分逻辑：判定规则、代理解析、
cookie 增删的隔离行为（用临时 sqlite 库模拟浏览器库）。
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import exhentai_unblock as eu  # noqa: E402


# ------------------------------------------------------------------ verdict

@pytest.mark.parametrize(
    "code,size,ign,expect_state",
    [
        (200, 33867, "jxqzc5sd7t9wkr1wb", "ok"),   # 正常页面 + 新 igneous
        (200, 33867, None, "ok"),                   # 正常页面、没下发 igneous
        (200, 0, "mystery", "banned"),              # 典型白屏
        (200, 0, None, "banned"),                   # 0 字节但没有 set-cookie
        (None, 0, None, "bad"),                     # 连不上
    ],
)
def test_verdict(code, size, ign, expect_state):
    state, msg = eu.verdict(code, size, ign)
    assert state == expect_state, msg


def test_verdict_banned_mentions_mystery():
    _, msg = eu.verdict(200, 0, "mystery")
    assert "mystery" in msg


# ------------------------------------------------------------------ 代理解析

def test_system_proxy_parses(monkeypatch):
    fake = (
        "<dictionary> {\n"
        "  HTTPEnable : 1\n"
        "  HTTPPort : 7890\n"
        "  HTTPProxy : 127.0.0.1\n"
        "}\n"
    )

    class R:
        stdout = fake

    monkeypatch.setattr(eu.subprocess, "run", lambda *a, **k: R())
    assert eu.system_proxy() == "http://127.0.0.1:7890"


def test_system_proxy_disabled(monkeypatch):
    class R:
        stdout = "<dictionary> {\n  HTTPEnable : 0\n}\n"

    monkeypatch.setattr(eu.subprocess, "run", lambda *a, **k: R())
    assert eu.system_proxy() is None


# ------------------------------------------------------------------ 删 cookie

def _make_db(path: Path, rows: list[tuple[str, str]]) -> None:
    """造一个最小 cookies 表，只含 host_key / name 两列就够测删除逻辑。"""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
    con.executemany("INSERT INTO cookies VALUES (?, ?)", rows)
    con.commit()
    con.close()


def test_delete_bad_igneous_only_removes_igneous(tmp_path, monkeypatch):
    db = tmp_path / "Cookies"
    _make_db(db, [
        (".exhentai.org", "igneous"),
        (".exhentai.org", "ipb_member_id"),
        (".exhentai.org", "ipb_pass_hash"),
        (".exhentai.org", "sk"),
        ("e-hentai.org", "igneous"),  # 表站同名字段不能被误删
    ])
    monkeypatch.setattr(eu, "cookie_db", lambda browser: db)

    n, left = eu.delete_bad_igneous("edge")

    assert n == 1
    assert "igneous" not in left
    assert set(left) == {"ipb_member_id", "ipb_pass_hash", "sk"}
    # 表站的 igneous 必须还在
    con = sqlite3.connect(db)
    hosts = {h for (h,) in con.execute(
        "SELECT host_key FROM cookies WHERE name='igneous'")}
    con.close()
    assert hosts == {"e-hentai.org"}


def test_delete_bad_igneous_makes_backup(tmp_path, monkeypatch):
    db = tmp_path / "Cookies"
    _make_db(db, [(".exhentai.org", "igneous")])
    monkeypatch.setattr(eu, "cookie_db", lambda browser: db)

    eu.delete_bad_igneous("edge")

    assert (tmp_path / "Cookies.bak_exh").exists()


def test_delete_bad_igneous_when_absent(tmp_path, monkeypatch):
    db = tmp_path / "Cookies"
    _make_db(db, [(".exhentai.org", "ipb_member_id")])
    monkeypatch.setattr(eu, "cookie_db", lambda browser: db)

    n, left = eu.delete_bad_igneous("edge")

    assert n == 0
    assert left == ["ipb_member_id"]


# ------------------------------------------------------------------ 浏览器选择

def test_pick_browser_prefers_requested(tmp_path, monkeypatch):
    def fake_read(name, hosts):
        if name == "chrome":
            return [{"name": "ipb_member_id", "value": "1"},
                    {"name": "ipb_pass_hash", "value": "h"}]
        if name == "edge":
            return [{"name": "ipb_member_id", "value": "2"},
                    {"name": "ipb_pass_hash", "value": "h2"}]
        return []

    monkeypatch.setattr(eu, "read_cookies", fake_read)
    name, ck = eu.pick_browser("chrome")
    assert name == "chrome"
    assert ck["ipb_member_id"] == "1"


def test_pick_browser_falls_back_when_preferred_empty(monkeypatch):
    def fake_read(name, hosts):
        if name == "edge":
            return []  # 首选浏览器没登录
        return [{"name": "ipb_member_id", "value": "9"},
                {"name": "ipb_pass_hash", "value": "h"}]

    monkeypatch.setattr(eu, "read_cookies", fake_read)
    name, _ = eu.pick_browser("edge")
    assert name == "chrome"


def test_pick_browser_requires_both_login_cookies(monkeypatch):
    # 只有 ipb_member_id、缺 pass_hash → 视为没登录，不能拿来探测
    monkeypatch.setattr(eu, "read_cookies",
                        lambda n, h: [{"name": "ipb_member_id", "value": "1"}])
    name, ck = eu.pick_browser("edge")
    assert name is None
    assert ck == {}
