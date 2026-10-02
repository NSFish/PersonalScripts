#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
workbuddy_checkin.py — WorkBuddy / CodeBuddy CN 每日签到命令行工具（零依赖，仅标准库）

登录完全由 DSH Desktop 的 shatyuka/dsh-llm-codebuddy 插件完成，本脚本只读它的凭证：
  凭证：~/.dsh/codebuddy-auth.json（可用 DSH_CODEBUDDY_AUTH_FILE 覆盖）
  凭证过期 -> 直接报错退出，不续期不登录，请回 dsh 插件里重新登录。

用法：
  python3 workbuddy_checkin.py            # 签到
  python3 workbuddy_checkin.py --check-only
  python3 workbuddy_checkin.py status     # 看 dsh 凭证是谁、剩多久过期
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASES = ["https://www.codebuddy.cn", "https://copilot.tencent.com"]

CHECKIN_PATH = "/v2/billing/meter/daily-checkin"
STATUS_PATHS = ("/v2/billing/meter/checkin-activity-status", "/v2/billing/meter/checkin-status")
BALANCE_PATH = "/v2/billing/meter/get-user-resource"
SUMMARY_PATH = "/billing/meter/get-user-resource-summary"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def cred_path() -> Path:
    override = os.environ.get("DSH_CODEBUDDY_AUTH_FILE") or os.environ.get("WORKBUDDY_CREDENTIALS")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".dsh/codebuddy-auth.json"


def load_dsh_credential():
    """只读 dsh 插件凭证。返回 (token, identity, storage, path)。过期/缺失抛 ValueError。"""
    p = cred_path()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"找不到 dsh 登录凭证：{p}\n请先在 DSH Desktop 里打开 CodeBuddy 插件并完成登录。")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise ValueError(f"dsh 凭证损坏（{p}）：{e}\n请在 dsh 插件里重新登录。")
    if not isinstance(d, dict) or not isinstance(d.get("auth"), dict):
        raise ValueError(f"dsh 凭证格式不对（{p}），请在 dsh 插件里重新登录。")
    auth = d["auth"]
    acct = d.get("account", {}) if isinstance(d.get("account"), dict) else {}
    token = auth.get("accessToken")
    if not isinstance(token, str) or not token.strip():
        raise ValueError(f"dsh 凭证缺少 accessToken（{p}），请在 dsh 插件里重新登录。")
    if not acct.get("uid"):
        raise ValueError(f"dsh 凭证缺少 uid（{p}），请在 dsh 插件里重新登录。")
    try:
        remain_ms = int(auth.get("expiresAt", 0)) - int(time.time() * 1000)
    except (TypeError, ValueError):
        raise ValueError(f"dsh 凭证 expiresAt 无效（{p}），请在 dsh 插件里重新登录。")
    if remain_ms <= 0:
        raise ValueError(f"dsh 登录凭证已过期（{p}），请在 DSH Desktop 的 CodeBuddy 插件里重新登录。")
    identity = {"uid": acct.get("uid", ""), "domain": auth.get("domain", "") or "",
                "enterpriseId": acct.get("enterpriseId", "") or ""}
    return token.strip(), identity, d, p


def build_headers(token: str, base: str, identity=None):
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json",
         "Content-Type": "application/json", "User-Agent": USER_AGENT,
         "Origin": base, "Referer": base + "/"}
    ident = identity or {}
    if ident.get("uid"):
        h["X-User-Id"] = ident["uid"]
    if ident.get("domain"):
        h["X-Domain"] = ident["domain"]
    if ident.get("enterpriseId"):
        h["X-Enterprise-Id"] = ident["enterpriseId"]
    return h


def post_json(url: str, headers: dict, timeout: int = 25):
    req = Request(url, data=b"{}", headers=headers, method="POST")
    try:
        with build_opener(NoRedirects).open(req, timeout=timeout) as resp:
            try:
                return resp.status, json.loads(resp.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(f"无效响应 {url}：{e}")
    except HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"code": e.code, "message": e.reason}
        return e.code, body
    except (URLError, TimeoutError, OSError) as e:
        raise ValueError(f"网络错误 {url}：{e}")


def is_true(v) -> bool:
    return v is True or v == 1 or (isinstance(v, str) and v.strip().lower() in {"true", "1"})


def get_status(base: str, headers: dict, timeout: int):
    for p in STATUS_PATHS:
        try:
            code, body = post_json(base + p, headers, timeout)
        except ValueError:
            continue
        if code == 200 and isinstance(body, dict) and body.get("code") == 0:
            data = body.get("data")
            if isinstance(data, dict) and ("today_checked_in" in data or "todayCheckedIn" in data):
                return data
    return None


def get_balance(base: str, headers: dict, timeout: int):
    try:
        code, body = post_json(base + BALANCE_PATH, headers, timeout)
        if code == 200 and body.get("code") == 0:
            resp = body.get("data", {}).get("Response", {}).get("Data")
            if isinstance(resp, dict) and resp.get("TotalDosage") is not None:
                return resp.get("TotalDosage")
    except ValueError:
        pass
    try:
        code, body = post_json(base + SUMMARY_PATH, headers, timeout)
        if code == 200 and isinstance(body.get("data"), dict):
            total, hit = 0, False
            for pkg in body["data"].get("Packages") or []:
                if isinstance(pkg, dict) and pkg.get("CycleRemainCapacity") is not None:
                    try:
                        total += int(float(pkg["CycleRemainCapacity"]))
                        hit = True
                    except (TypeError, ValueError):
                        continue
            if hit:
                return total
    except ValueError:
        pass
    return None


def do_checkin(base: str, headers: dict, timeout: int):
    code, body = post_json(base + CHECKIN_PATH, headers, timeout)
    if not isinstance(body, dict):
        return "failed", f"HTTP {code} 无效响应", body
    msg = str(body.get("msg") or body.get("message") or "")
    c = body.get("code")
    if code == 200 and (c in (0, 200) or "成功" in msg):
        return "ok", msg or "签到成功", body
    if c == 10001 or "已签到" in msg or "请明天" in msg:
        return "already", msg or "今日已签", body
    if any(k in msg for k in ("失效", "过期", "无效", "expired", "invalid", "登录")) or code in (401, 403):
        return "expired", msg or f"Token 失效（HTTP {code}）", body
    if code == 200:
        return "already", msg or "今日已签（推断）", body
    return "failed", f"HTTP {code} {msg}", body


def cmd_status(args) -> int:
    try:
        _, _, st, p = load_dsh_credential()
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    auth, acct = st["auth"], st.get("account", {})
    try:
        remain_s = (int(auth.get("expiresAt", 0)) - int(time.time() * 1000)) // 1000
    except (TypeError, ValueError):
        remain_s = 0
    out = {"nickname": acct.get("nickname"), "uid": acct.get("uid"),
           "domain": auth.get("domain"), "expires_in_s": max(remain_s, 0),
           "credential": str(p)}
    if args.as_json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"✅ dsh 凭证：{out['nickname']}（uid={out['uid']}），还剩约 {out['expires_in_s']}s（{p}）")
    return 0


def cmd_checkin(args) -> int:
    try:
        token, ident, _, p = load_dsh_credential()
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    if len(token) < 20:
        print(f"❌ dsh 凭证 accessToken 过短（{p}），请在 dsh 插件里重新登录。", file=sys.stderr)
        return 2
    source = f"dsh:{p}"
    bases = [args.host] if args.host else BASES
    last_err = ""
    for base in bases:
        base = base.rstrip("/")
        headers = build_headers(token, base, ident)
        try:
            status = get_status(base, headers, args.timeout)
            if args.check_only:
                balance = get_balance(base, headers, args.timeout)
                out = {"host": base, "token_source": source,
                       "today_checked_in": (status.get("today_checked_in", status.get("todayCheckedIn")) if status else None),
                       "today_credit": (status.get("today_credit") or status.get("daily_credit")) if status else None,
                       "total_credits": status.get("total_credits") if status else None,
                       "streak_days": status.get("streak_days") if status else None,
                       "activity_name": status.get("activity_name") if status else None,
                       "balance": balance}
                if args.as_json:
                    print(json.dumps(out, ensure_ascii=False))
                else:
                    flag = "✅ 已签" if is_true(out["today_checked_in"]) else ("⬜ 未签" if out["today_checked_in"] is False else "❓ 未知")
                    print(f"{flag}（{base}，来源 {source}）")
                    print(f"• 本次积分：{out['today_credit']}")
                    print(f"• 累计签到：{out['total_credits']}")
                    print(f"• 连续天数：{out['streak_days']}")
                    print(f"• 当前活动：{out['activity_name']}")
                    print(f"• 账户余额：{out['balance']}")
                return 0
            state, msg, raw = do_checkin(base, headers, args.timeout)
            status2 = get_status(base, headers, args.timeout) or status or {}
            balance = get_balance(base, headers, args.timeout)
            body_data = raw.get("data") if isinstance(raw, dict) else None
            out = {"host": base, "token_source": source, "result": state, "message": msg,
                   "today_credit": status2.get("today_credit") or status2.get("daily_credit")
                   or (body_data.get("credit") if isinstance(body_data, dict) else None),
                   "total_credits": status2.get("total_credits"),
                   "streak_days": status2.get("streak_days")
                   or (body_data.get("streak_days") if isinstance(body_data, dict) else None),
                   "activity_name": status2.get("activity_name"), "balance": balance}
            if args.as_json:
                print(json.dumps(out, ensure_ascii=False))
            else:
                icon = {"ok": "✅", "already": "🟢", "expired": "⚠️", "failed": "❌"}[state]
                title = {"ok": "签到完成", "already": "今天已签到过",
                         "expired": "Token 失效", "failed": "签到失败"}[state]
                print(f"{icon} {title}：{msg}（{base}）")
                print(f"• 本次签到获得：{out['today_credit']} 积分")
                print(f"• 累计签到获得：{out['total_credits']} 积分")
                print(f"• 当前余额：{out['balance']} 积分")
                print(f"• 连续天数：{out['streak_days']} 天")
                print(f"• 当前活动：{out['activity_name']}")
                if state == "expired":
                    print("提示：dsh 凭证被拒，请在 DSH Desktop 的 CodeBuddy 插件里重新登录。", file=sys.stderr)
            return {"ok": 0, "already": 0, "expired": 2, "failed": 1}[state]
        except ValueError as e:
            last_err = str(e)
            continue
    print(f"❌ 签到失败：{last_err or '网络异常'}", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="WorkBuddy 签到 CLI（复用 DSH Desktop 插件凭证，只读不写）",
                                 prog="workbuddy_checkin.py")
    ap.add_argument("command", nargs="?", default="checkin", choices=["status", "checkin"],
                    help="status=看 dsh 凭证，checkin=签到（默认）")
    ap.add_argument("--status", action="store_true", help="等价于 status")
    ap.add_argument("--host", help="指定域名")
    ap.add_argument("--check-only", action="store_true", help="只查状态不签到")
    ap.add_argument("--json", dest="as_json", action="store_true")
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args(argv)

    if args.status and args.command == "checkin":
        return cmd_status(args)
    if args.command == "status":
        return cmd_status(args)
    return cmd_checkin(args)


if __name__ == "__main__":
    raise SystemExit(main())
