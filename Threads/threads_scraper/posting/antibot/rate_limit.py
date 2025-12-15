import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional


LIMITS_DIR = os.path.join(os.path.dirname(__file__), "limits")
os.makedirs(LIMITS_DIR, exist_ok=True)


def _path(account_id: str) -> str:
    safe = account_id.replace("/", "_")
    return os.path.join(LIMITS_DIR, f"{safe}.json")


def _utc_now_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_state(account_id: str) -> Dict[str, Any]:
    path = _path(account_id)
    if not os.path.exists(path):
        return {
            "last_post_ts": 0.0,
            "hour_count": 0,
            "hour_window_start": 0.0,
            "day_count": 0,
            "day_ymd": "",
            "last_risk_level": "NONE",
            "last_risk_ts": 0.0,
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "last_post_ts": 0.0,
            "hour_count": 0,
            "hour_window_start": 0.0,
            "day_count": 0,
            "day_ymd": "",
            "last_risk_level": "NONE",
            "last_risk_ts": 0.0,
        }


def _write_state(account_id: str, state: Dict[str, Any]) -> None:
    path = _path(account_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _ymd(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d")


def check(account_id: str, now_ts: float, mode: str, min_interval_sec: int, hour_cap: int, day_cap: int, *, enforce_r3: bool = False, cooldown_on_r3_s: Optional[int] = None) -> Dict[str, Any]:
    state = _read_state(account_id)
    reason = "ok"
    next_try_eta = None

    # min interval
    last_ts = float(state.get("last_post_ts", 0.0))
    since_last = now_ts - last_ts if last_ts else None
    if last_ts and since_last is not None and since_last < float(min_interval_sec):
        reason = "min_interval"
        next_try_eta = _utc_now_iso(last_ts + float(min_interval_sec))

    # hour window
    hour_start = float(state.get("hour_window_start", 0.0))
    hour_count = int(state.get("hour_count", 0))
    if not hour_start or now_ts - hour_start >= 3600.0:
        # reset window
        hour_start = now_ts - (now_ts % 3600.0)
        hour_count = 0
    if hour_count >= int(hour_cap) and reason == "ok":
        reason = "hour_cap"
        next_try_eta = _utc_now_iso(hour_start + 3600.0)

    # day window
    day_ymd = state.get("day_ymd") or ""
    day_count = int(state.get("day_count", 0))
    cur_day = _ymd(now_ts)
    if day_ymd != cur_day:
        day_ymd = cur_day
        day_count = 0
    if day_count >= int(day_cap) and reason == "ok":
        reason = "day_cap"
        # next day 00:00 UTC
        dt_now = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        next_day = (dt_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_try_eta = next_day.strftime("%Y-%m-%dT%H:%M:%SZ")

    # R3 cooldown enforcement (optional)
    if enforce_r3:
        last_risk_level = str(state.get("last_risk_level") or "NONE").upper()
        last_risk_ts = float(state.get("last_risk_ts") or 0.0)
        cd = int(cooldown_on_r3_s or 0)
        if last_risk_level == "R3" and last_risk_ts and (now_ts - last_risk_ts) < cd and reason == "ok":
            reason = "r3_cooldown"
            next_try_eta = _utc_now_iso(last_risk_ts + cd)

    allowed = True if mode in ("off", "observe") else (reason == "ok")

    return {
        "allowed": allowed,
        "reason": reason,
        "next_try_eta": next_try_eta,
        "counters": {
            "last_post_ts": last_ts,
            "hour_count": hour_count,
            "day_count": day_count,
        },
        "windows": {
            "hour_window_start": hour_start,
            "day_ymd": day_ymd,
        },
        "risk": {
            "last_risk_level": state.get("last_risk_level", "NONE"),
            "last_risk_ts": state.get("last_risk_ts", 0.0),
        },
    }


def update_counters(account_id: str, now_ts: float) -> Dict[str, Any]:
    """在成功發文後呼叫：更新 last_post_ts、hour/day 計數並持久化。"""
    state = _read_state(account_id)
    # hour window
    hour_start = float(state.get("hour_window_start", 0.0))
    hour_count = int(state.get("hour_count", 0))
    if not hour_start or now_ts - hour_start >= 3600.0:
        hour_start = now_ts - (now_ts % 3600.0)
        hour_count = 0
    hour_count += 1

    # day window
    cur_day = _ymd(now_ts)
    day_ymd = state.get("day_ymd") or ""
    day_count = int(state.get("day_count", 0))
    if day_ymd != cur_day:
        day_ymd = cur_day
        day_count = 0
    day_count += 1

    state.update({
        "last_post_ts": now_ts,
        "hour_window_start": hour_start,
        "hour_count": hour_count,
        "day_ymd": day_ymd,
        "day_count": day_count,
    })
    _write_state(account_id, state)
    return state


def update_last_risk(account_id: str, level: str, now_ts: float) -> Dict[str, Any]:
    """在檢測到風險後呼叫：持久化最後風險等級與時間。"""
    state = _read_state(account_id)
    state.update({
        "last_risk_level": str(level or "NONE").upper(),
        "last_risk_ts": float(now_ts),
    })
    _write_state(account_id, state)
    return state
