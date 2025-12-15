from typing import Dict, Optional


def recommend_cooldown(now_ts: float, last_post_ts: Optional[float], policy: Optional[Dict] = None) -> Dict:
    """基於簡單策略建議冷卻時間，不阻擋流程。
    policy 可包含 min_interval_sec/hour_cap/day_cap 等，僅做提示用途。
    回傳 {"suggested_sleep_s": N, "reason": "min_interval|hour_cap|day_cap|none"}
    """
    policy = policy or {}
    min_interval = int(policy.get("min_interval_sec", 0) or 0)
    hour_cap = int(policy.get("hour_cap", 0) or 0)
    day_cap = int(policy.get("day_cap", 0) or 0)

    if not last_post_ts:
        return {"suggested_sleep_s": 0, "reason": "none"}

    elapsed = int(now_ts - last_post_ts)
    # 最低間隔建議
    if min_interval > 0 and elapsed < min_interval:
        return {"suggested_sleep_s": max(0, min_interval - elapsed), "reason": "min_interval"}

    # 其餘 cap 僅提示（實務上需統計當前小時/日次數；此處留白給上層）
    return {"suggested_sleep_s": 0, "reason": "none"}
