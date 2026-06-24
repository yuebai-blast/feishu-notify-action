#!/usr/bin/env python3
"""流水线信使：把 GitHub Actions 流水线结果以飞书自建应用私聊卡片推送给指定用户。

被本仓库的 composite action（action.yml）调用，所有参数经环境变量注入：
机密（App ID/Secret/收件人）来自调用方 secrets，绝不写入仓库；其余字段来自 workflow_run 上下文。
失败时会用 GITHUB_TOKEN 查一次 jobs API，补上「哪个 job 的哪个 step 挂了」。
"""
from __future__ import annotations

import os
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

FEISHU = "https://open.feishu.cn/open-apis"
GH_API = os.environ.get("GITHUB_API_URL", "https://api.github.com")

# 视作「失败」的所有结论
BAD = {"failure", "timed_out", "cancelled", "startup_failure", "action_required"}
ZH_STATUS = {
    "success": "成功",
    "failure": "失败",
    "cancelled": "已取消",
    "timed_out": "超时",
    "skipped": "跳过",
    "startup_failure": "启动失败",
    "action_required": "需人工处理",
}


def http(url: str, payload: dict | None = None, headers: dict | None = None, method: str = "GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}


def fmt_time(iso: str, tz: str) -> str:
    if not iso:
        return "-"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    if ZoneInfo and tz:
        try:
            dt = dt.astimezone(ZoneInfo(tz))
        except Exception:
            pass
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def duration(start: str, end: str) -> str:
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
        secs = int((e - s).total_seconds())
        if secs < 0:
            return "-"
        m, sec = divmod(secs, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h} 小时 {m} 分 {sec} 秒"
        if m:
            return f"{m} 分 {sec} 秒"
        return f"{sec} 秒"
    except Exception:
        return "-"


def failure_reason(repo: str, run_id: str, token: str) -> str:
    """查 jobs API，拼出失败的 job → step。"""
    if not (repo and run_id and token):
        return ""
    status, data = http(
        f"{GH_API}/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if status != 200:
        return ""
    reasons = []
    for job in data.get("jobs", []):
        if job.get("conclusion") in BAD:
            bad_steps = [s["name"] for s in job.get("steps", []) if s.get("conclusion") in BAD]
            if bad_steps:
                reasons.append(f"Job「{job['name']}」→ 步骤「{bad_steps[0]}」")
            else:
                reasons.append(f"Job「{job['name']}」({job.get('conclusion')})")
    return "；".join(reasons[:3])


def main() -> int:
    app_id = os.environ["FEISHU_APP_ID"]
    app_secret = os.environ["FEISHU_APP_SECRET"]
    receive_id = os.environ["FEISHU_RECEIVE_ID"]
    rtype = os.environ.get("FEISHU_RECEIVE_ID_TYPE", "open_id")

    status = os.environ.get("STATUS", "")
    name = os.environ.get("WORKFLOW_NAME", "")
    repo = os.environ.get("REPO", "")
    branch = os.environ.get("BRANCH", "")
    event = os.environ.get("EVENT", "")
    actor = os.environ.get("ACTOR", "")
    run_url = os.environ.get("RUN_URL", "")
    run_id = os.environ.get("RUN_ID", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    sha = os.environ.get("COMMIT_SHA", "")[:7]
    msg_lines = (os.environ.get("COMMIT_MESSAGE", "") or "").strip().splitlines()
    msg = msg_lines[0] if msg_lines else ""
    author = os.environ.get("COMMIT_AUTHOR", "")
    tz = os.environ.get("TIMEZONE", "Asia/Shanghai")
    started = os.environ.get("RUN_STARTED_AT", "")
    updated = os.environ.get("RUN_UPDATED_AT", "")

    ok = status == "success"
    template = "green" if ok else "red"
    icon = "✅" if ok else "❌"
    title = f"{icon} {name} · {ZH_STATUS.get(status, status or '结束')}"

    lines = [
        f"**仓库**：{repo}",
        f"**分支 / Tag**：{branch}　**触发**：{event} · by {actor}",
        f"**提交**：`{sha}`" + (f" — {author}" if author else ""),
    ]
    if msg:
        lines.append(f"**说明**：{msg}")
    lines += [
        f"**开始**：{fmt_time(started, tz)}",
        f"**结束**：{fmt_time(updated, tz)}　**耗时**：{duration(started, updated)}",
    ]
    if not ok:
        reason = failure_reason(repo, run_id, token)
        if reason:
            lines.append(f"**失败位置**：{reason}")

    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}]
    if run_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看运行详情"},
                "url": run_url,
                "type": "primary",
            }],
        })
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"时间基于 {tz}"}]})

    card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}, "template": template},
        "elements": elements,
    }

    s, token_res = http(
        f"{FEISHU}/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
        method="POST",
    )
    tat = token_res.get("tenant_access_token")
    if not tat:
        print(f"获取飞书 token 失败: {token_res}", file=sys.stderr)
        return 1

    s, res = http(
        f"{FEISHU}/im/v1/messages?receive_id_type={rtype}",
        {"receive_id": receive_id, "msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)},
        {"Authorization": f"Bearer {tat}"},
        method="POST",
    )
    if res.get("code") != 0:
        print(f"发送失败: {res}", file=sys.stderr)
        return 1
    print(f"已推送: message_id={res['data']['message_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
