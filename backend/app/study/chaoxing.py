"""学习通网页会话：扫码登录 + 作业列表读取。

只做两件事：登录拿 cookie、读作业列表。不碰视频/答题/签到/提交。
请求头完全按浏览器来，不用 httpx 默认 UA。接口地址集中在顶部，
平台改版时改这里就行。网页会话和手机 APP 相互独立，不做踢下线。
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from . import store

BASE = "https://passport2.chaoxing.com"
MOBILE = "https://mooc1.chaoxing.com"

# 浏览器请求头，别用 httpx 默认的 python-httpx
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# 这些是网页版未公开接口，平台可能调整路径，集中在这里方便改
QR_START = f"{BASE}/qrcodeLogin"
QR_POLL = f"{BASE}/qrcodeLogin/check"
ASSIGNMENTS = f"{MOBILE}/mooc-ans/interaction/assignment/student/list"

TIMEOUT = 15.0


class SessionExpired(Exception):
    """登录失效 / 401：调用方要停本次同步并弹窗，不重试。"""


def _client(cookie: str = "") -> httpx.Client:
    h = dict(HEADERS)
    if cookie:
        h["Cookie"] = cookie
    return httpx.Client(headers=h, timeout=TIMEOUT, follow_redirects=True)


def _check(res: httpx.Response) -> None:
    """401 或返回体里带登录失效字样，统一抛 SessionExpired。"""
    if res.status_code in (401, 403):
        raise SessionExpired(f"HTTP {res.status_code}")
    text = res.text[:500]
    if any(k in text for k in ("登录失效", "未登录", "请先登录", "loginExpired", "请重新登录")):
        raise SessionExpired("接口返回登录失效")


def start_qr() -> dict[str, Any]:
    """拿扫码登录的二维码。返回 qrcode 图片 URL 和本次的轮询标识。"""
    with _client() as c:
        res = c.get(QR_START)
        _check(res)
        data: dict[str, Any] = {}
        try:
            data = res.json()
        except ValueError:
            pass
        # 不同版本返回字段不一样，这里都兜一下
        key = str(data.get("uuid") or data.get("qruuid") or data.get("token") or "")
        img = str(data.get("qrcode") or data.get("qrCode") or data.get("image") or "")
        if not key or not img:
            raise ValueError("学习通没返回二维码，接口可能改版了")
        return {"key": key, "image": img}


def poll_qr(key: str) -> dict[str, Any]:
    """轮询扫码结果。status: waiting / scanned / expired / ok。"""
    with _client() as c:
        res = c.get(QR_POLL, params={"uuid": key, "t": int(time.time())})
        _check(res)
        try:
            data = res.json()
        except ValueError as e:  # noqa: BLE001
            raise ValueError("扫码状态返回不是 JSON") from e
        status = str(data.get("status") or data.get("result") or "waiting")
        if status in ("success", "ok", "1", "2"):
            cookies = c.cookies.jar
            cookie_str = "; ".join(f"{x.name}={x.value}" for x in cookies)
            if not cookie_str:
                # 有些版本把 cookie 放在返回体里
                cookie_str = str(data.get("cookie") or "")
            if not cookie_str:
                raise ValueError("登录成功但没拿到 cookie")
            store.set_cookie(cookie_str)
            return {"status": "ok"}
        if status in ("expired", "-1", "-2"):
            return {"status": "expired"}
        if status in ("scanned", "waiting", "0"):
            return {"status": "scanned" if status == "scanned" else "waiting"}
        return {"status": "waiting"}


def _parse_assignments(data: Any) -> list[dict[str, Any]]:
    """把不同版本的作业结构统一成 {id,title,due_at}。"""
    rows = data if isinstance(data, list) else (
        data.get("list") or data.get("data") or data.get("rows") or []
        if isinstance(data, dict) else []
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or r.get("name") or r.get("taskName") or "").strip()
        if not title:
            continue
        raw = r.get("dueAt") or r.get("deadline") or r.get("endTime") or r.get("dueTime")
        due = _to_ts(raw)
        aid = str(r.get("id") or r.get("taskId") or r.get("assignmentId") or title)
        out.append({"id": aid, "title": title, "due_at": due})
    return out


def _to_ts(raw: Any) -> float | None:
    if raw in (None, "", 0):
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        return v / 1000 if v > 1e11 else v
    s = str(raw).strip().replace("T", " ").replace("Z", "")
    from datetime import datetime

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(s[:19] if len(s) >= 19 else s, fmt).timestamp()
        except ValueError:
            continue
    return None


def fetch_assignments() -> list[dict[str, Any]]:
    """只读作业列表。登录失效抛 SessionExpired，其它异常原样往上抛。"""
    cookie = store.cookie()
    if not cookie:
        raise SessionExpired("还没扫码登录")
    with _client(cookie) as c:
        res = c.get(ASSIGNMENTS, headers={"Referer": f"{MOBILE}/mooc-ans/"})
        _check(res)
        try:
            data = res.json()
        except ValueError as e:  # noqa: BLE001
            raise ValueError("作业列表返回不是 JSON，接口可能改版") from e
        return _parse_assignments(data)
