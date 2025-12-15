import json
import os
import time
from typing import List, Dict


def convert_cookies_to_storage_state(cookies_in: str, storage_out: str) -> None:
    """Convert a list of cookies (Selenium/Scrapy format) to Playwright storage_state.json.

    This is a best-effort conversion supporting common fields.
    """
    with open(cookies_in, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("cookies input must be a list")

    now = int(time.time())
    out: Dict[str, List[Dict]] = {"cookies": [], "origins": []}
    for c in data:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        domain = c.get("domain") or ".threads.net"
        path = c.get("path") or "/"
        exp = c.get("expiry") or c.get("expires") or (now + 30 * 24 * 3600)
        http_only = bool(c.get("httpOnly", False))
        secure = bool(c.get("secure", True))
        out["cookies"].append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "expires": int(exp) if isinstance(exp, (int, float)) else now + 30 * 24 * 3600,
            "httpOnly": http_only,
            "secure": secure,
            "sameSite": "Lax",
        })

    os.makedirs(os.path.dirname(storage_out), exist_ok=True)
    with open(storage_out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
