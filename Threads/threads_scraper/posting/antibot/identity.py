import random
from typing import Dict


def build_identity(headless: bool = True) -> Dict:
    # 少量真實 UA 範本（桌機 Chrome）
    ua_pool = [
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.70 Safari/537.36"
        ),
    ]
    ua = random.choice(ua_pool)

    # viewport 與縮放
    viewport = {"width": random.choice([1200, 1366, 1440]), "height": random.choice([800, 900, 960])}
    dpr = random.choice([1, 2])

    # Accept-Language 與 sec-ch-ua
    accept_lang = "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    sec_ch_ua = '"Chromium";v="120", "Not=A?Brand";v="24", "Google Chrome";v="120"'
    sec_ch_platform = '"macOS"'

    return {
        "user_agent": ua,
        "viewport": viewport,
        "device_scale_factor": dpr,
        "locale": "zh-TW",
        "timezone_id": "Asia/Taipei",
        "headers": {
            "Accept-Language": accept_lang,
            "sec-ch-ua": sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": sec_ch_platform,
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://www.threads.net/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },
        "platform": "MacIntel",
        "languages": ["zh-TW", "zh", "en-US", "en"],
    }
