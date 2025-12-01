import json
import os
import time


def to_storage_state(selenium_cookies_path: str, storage_state_path: str) -> None:
    """
    將 Selenium cookies.json 轉為 Playwright 可用的 storage_state.json

    :param selenium_cookies_path: Selenium 匯出的 cookies.json 路徑
    :param storage_state_path: 目標 storage_state.json 輸出路徑
    """
    with open(selenium_cookies_path, "r", encoding="utf-8") as f:
        selenium_cookies = json.load(f)
        if not selenium_cookies:
            selenium_cookies = []
        if not isinstance(selenium_cookies, list):
            # 嘗試由物件取值；否則視為空
            selenium_cookies = selenium_cookies.get("cookies", []) if isinstance(selenium_cookies, dict) else []

    cookies = []
    for c in selenium_cookies:
        if not c or not c.get("name") or not c.get("value"):
            continue
        cookies.append({
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".threads.net"),
            "path": c.get("path", "/"),
            "expires": int(c.get("expiry", time.time() + 3600)) if c.get("expiry") else int(time.time() + 3600),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", True)),
            "sameSite": "Lax",
        })

    storage_state = {"cookies": cookies, "origins": []}

    os.makedirs(os.path.dirname(storage_state_path), exist_ok=True)
    with open(storage_state_path, "w", encoding="utf-8") as f:
        json.dump(storage_state, f, ensure_ascii=False)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Convert Selenium cookies.json to Playwright storage_state.json")
    ap.add_argument("--in", dest="inp", default="Threads/threads_scraper/cookies.json")
    ap.add_argument("--out", dest="out", default="Threads/threads_scraper/storage_state.json")
    args = ap.parse_args()

    to_storage_state(args.inp, args.out)
    print(f"[OK] storage_state written to {args.out}")
