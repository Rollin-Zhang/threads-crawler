import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any


PERSONAS_DIR = os.path.join(os.path.dirname(__file__), "personas")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _persona_path(account_id: str) -> str:
    os.makedirs(PERSONAS_DIR, exist_ok=True)
    safe = account_id.replace("/", "_")
    return os.path.join(PERSONAS_DIR, f"{safe}.json")


def _default_persona(account_id: str, ttl_days: int) -> Dict[str, Any]:
    # 基礎預設（首次生成）：合理 UA、固定語系/時區/平台，視窗大小常見值
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    sec_ch_ua = '"Chromium";v="120", "Google Chrome";v="120", ";Not A Brand";v="99"'
    ts = _utc_now_iso()
    return {
        "version": 1,
        "account_id": account_id,
        "created_at": ts,
        "last_rotated_at": ts,
        "ttl_days": ttl_days,
        "user_agent": ua,
        "sec_ch_ua": sec_ch_ua,
        "accept_language": "zh-TW,zh;q=0.9,en-US;q=0.8",
        "timezone_id": "Asia/Taipei",
        "platform": "MacIntel",
        "languages": ["zh-TW", "zh", "en-US"],
        "viewport": {"width": 1440, "height": 900, "device_scale_factor": 2},
        "webgl_vendor": "Apple",
        "webgl_renderer": "ANGLE (Apple MTL, Apple M2)",
        "fingerprint_noise_seed": int(time.time()) % 100000,
        "persona_mode": "sticky",
    }


def save_persona(account_id: str, persona: Dict[str, Any]) -> str:
    path = _persona_path(account_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(persona, f, ensure_ascii=False, indent=2)
    return path


def _micro_drift(old: Dict[str, Any]) -> Dict[str, Any]:
    # 僅做小幅變動：viewport ±0..20px、noise_seed 輕微調整
    vp = dict(old.get("viewport", {}))
    w = vp.get("width", 1440)
    h = vp.get("height", 900)
    dpr = vp.get("device_scale_factor", 2)

    def clamp(val, base, span=20):
        return max(base - span, min(base + span, val))

    # 使用時間為種子，產生微小偏移
    t = int(time.time())
    dw = (t % 7) - 3  # -3..+3
    dh = ((t // 7) % 7) - 3
    new_w = clamp(w + dw, w)
    new_h = clamp(h + dh, h)

    old["viewport"] = {"width": new_w, "height": new_h, "device_scale_factor": dpr}
    old["fingerprint_noise_seed"] = (old.get("fingerprint_noise_seed", 12345) + (t % 13)) % 100000
    old["last_rotated_at"] = _utc_now_iso()

    # UA 小版本位移（例如 Chrome/120.0.0.0 -> 120.0.0.1）
    ua = old.get("user_agent", "")
    try:
        import re
        m = re.search(r"Chrome/(\d+)\.(\d+)\.(\d+)\.(\d+)", ua)
        if m:
            a, b, c, d = map(int, m.groups())
            d = (d + 1) % 10  # 輕微遞增
            new_ver = f"{a}.{b}.{c}.{d}"
            ua = re.sub(r"Chrome/\d+\.\d+\.\d+\.\d+", f"Chrome/{new_ver}", ua)
            old["user_agent"] = ua
            # 同步 sec_ch_ua 版本
            old["sec_ch_ua"] = f'"Chromium";v="{a}", "Google Chrome";v="{a}", ";Not A Brand";v="99"'
    except Exception:
        pass
    return old


def load_or_create_persona(account_id: str, ttl_days: int = 7, mode: str = "sticky") -> Dict[str, Any]:
    path = _persona_path(account_id)
    persona: Dict[str, Any]
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                persona = json.load(f)
        except Exception:
            persona = _default_persona(account_id, ttl_days)
    else:
        persona = _default_persona(account_id, ttl_days)

    persona["persona_mode"] = mode or persona.get("persona_mode", "sticky")

    # 依 persona_mode 與 ttl 檢查是否需要輪替
    try:
        last = datetime.strptime(persona.get("last_rotated_at"), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        last = datetime.now(timezone.utc)
    now = datetime.now(timezone.utc)
    ttl = int(persona.get("ttl_days", ttl_days))

    need_rotate = False
    if persona.get("persona_mode") == "daily":
        need_rotate = (now.date() != last.date())
    elif persona.get("persona_mode") == "random":
        need_rotate = True
    else:  # sticky
        need_rotate = (now - last >= timedelta(days=ttl))

    if need_rotate:
        persona = _micro_drift(persona)
        save_persona(account_id, persona)
    else:
        # 確保檔案存在
        if not os.path.exists(path):
            save_persona(account_id, persona)
    return persona
