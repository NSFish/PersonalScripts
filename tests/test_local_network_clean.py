"""local_network_clean 的回归测试。

用临时目录里伪造的 networkextension plist（NSKeyedArchiver 结构）跑脚本，
不碰系统那份 /Library/Preferences/com.apple.networkextension.plist。
"""
import plistlib
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"
SCRIPT = SRC / "local_network_clean.py"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def make_plist(rule_paths: list[str | None]) -> dict:
    """伪造一份 networkextension plist：顶层 root 指向 network privacy 配置。"""
    objs: list = ["$null"]

    def add(obj):
        objs.append(obj)
        return plistlib.UID(len(objs) - 1)

    cls_rule = add({"$classname": "NEPathRule",
                    "$classes": ["NEPathRule", "NEAppRule", "NSObject"]})
    cls_array = add({"$classname": "NSArray", "$classes": ["NSArray", "NSObject"]})
    cls_conf = add({"$classname": "NEConfiguration",
                    "$classes": ["NEConfiguration", "NSObject"]})
    cls_ctrl = add({"$classname": "NEPathController",
                    "$classes": ["NEPathController", "NSObject"]})

    rule_uids = []
    for path in rule_paths:
        rule = {
            "$class": cls_rule,
            "Path": add(path) if path is not None else plistlib.UID(0),
            "DenyMulticast": False,
        }
        rule_uids.append(add(rule))

    array = add({"$class": cls_array, "NS.objects": rule_uids})
    controller = add({"$class": cls_ctrl, "Rules": array})
    conf = add({
        "$class": cls_conf,
        "Name": add("com.apple.preferences.networkprivacy-TEST"),
        "PathController": controller,
    })
    return {
        "$archiver": "NSKeyedArchiver",
        "$version": 100000,
        "$top": {"root": conf},
        "$objects": objs,
    }


def write_plist(path: Path, rule_paths: list[str | None]) -> None:
    with path.open("wb") as f:
        plistlib.dump(make_plist(rule_paths), f, fmt=plistlib.FMT_BINARY)


def read_paths(path: Path) -> list[str | None]:
    """读回规则数组里每条规则的 Path（None 表示无路径的默认规则）。"""
    with path.open("rb") as f:
        plist = plistlib.load(f)
    objs = plist["$objects"]

    def ref(v):
        return objs[v] if isinstance(v, plistlib.UID) else v

    conf = ref(plist["$top"]["root"])
    controller = ref(conf["PathController"])
    array = ref(controller["Rules"])
    out = []
    for item in array["NS.objects"]:
        rule = ref(item)
        value = ref(rule["Path"])
        out.append(value if isinstance(value, str) and value != "$null" else None)
    return out


def test_dry_run_reports_stale_only_and_changes_nothing(tmp_path: Path):
    existing = tmp_path / "Real.app" / "Contents/MacOS/Real"
    existing.parent.mkdir(parents=True)
    existing.write_text("x")
    clone = tmp_path / "code_sign_clone" / "aaa" / "Clone.app" / "Contents/MacOS/Clone"
    clone.parent.mkdir(parents=True)
    clone.write_text("x")
    gone = "/Applications/Gone.app/Contents/MacOS/Gone"

    plist = tmp_path / "com.apple.networkextension.plist"
    write_plist(plist, [str(existing), str(clone), gone, None])
    before = plist.read_bytes()

    r = run("--dry-run", "--plist", str(plist))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "待清理 2 条" in r.stdout
    assert str(clone) in r.stdout and "签名副本" in r.stdout
    assert gone in r.stdout and "App 已不存在" in r.stdout
    assert str(existing) in r.stdout
    assert plist.read_bytes() == before  # dry-run 不碰文件


def test_apply_removes_stale_and_keeps_real(tmp_path: Path):
    existing = tmp_path / "Real.app" / "Contents/MacOS/Real"
    existing.parent.mkdir(parents=True)
    existing.write_text("x")
    clone = tmp_path / "code_sign_clone" / "aaa" / "Clone.app" / "Contents/MacOS/Clone"
    clone.parent.mkdir(parents=True)
    clone.write_text("x")
    gone = "/Applications/Gone.app/Contents/MacOS/Gone"

    plist = tmp_path / "com.apple.networkextension.plist"
    write_plist(plist, [str(existing), str(clone), gone, None])

    r = run("--plist", str(plist))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "已清理 2 条" in r.stdout
    assert read_paths(plist) == [str(existing), None]  # 无路径的默认规则保留

    backups = list(tmp_path.glob("com.apple.networkextension.plist.bak.*"))
    assert len(backups) == 1, "应留下一个备份"


def test_keep_clone_keeps_existing_clone(tmp_path: Path):
    existing = tmp_path / "Real.app" / "Contents/MacOS/Real"
    existing.parent.mkdir(parents=True)
    existing.write_text("x")
    clone = tmp_path / "code_sign_clone" / "aaa" / "Clone.app" / "Contents/MacOS/Clone"
    clone.parent.mkdir(parents=True)
    clone.write_text("x")

    plist = tmp_path / "com.apple.networkextension.plist"
    write_plist(plist, [str(existing), str(clone)])

    r = run("--plist", str(plist), "--keep-clone")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "已清理 0 条" not in r.stdout
    assert read_paths(plist) == [str(existing), str(clone)]


def test_missing_plist_exits_nonzero(tmp_path: Path):
    r = run("--plist", str(tmp_path / "nope.plist"))
    assert r.returncode != 0
    assert "找不到" in r.stderr


def test_plist_without_privacy_config_exits_nonzero(tmp_path: Path):
    plist = tmp_path / "com.apple.networkextension.plist"
    with plist.open("wb") as f:
        plistlib.dump({"$archiver": "NSKeyedArchiver", "$version": 100000,
                       "$top": {}, "$objects": ["$null"]}, f, fmt=plistlib.FMT_BINARY)

    r = run("--plist", str(plist))
    assert r.returncode != 0
    assert "没有「本地网络」配置" in r.stderr


def test_escalation_command_quotes_and_escapes():
    """授权框命令要能安全带上带空格/引号的参数。"""
    import shlex

    sys.path.insert(0, str(SRC))
    import local_network_clean as lnc

    cmd = lnc.escalation_command(["--plist", "/tmp/a b/it's.plist"])
    prefix = 'do shell script "'
    suffix = '" with administrator privileges'
    assert cmd.startswith(prefix) and cmd.endswith(suffix)
    inner = cmd[len(prefix):-len(suffix)]
    assert '"' not in inner.replace('\\"', "")  # AppleScript 字符串里不能有裸双引号
    # 去掉 AppleScript 转义后，参数应原样交给 shell
    unescaped = inner.replace('\\"', '"').replace("\\\\", "\\")
    assert unescaped.endswith(shlex.quote("/tmp/a b/it's.plist"))

