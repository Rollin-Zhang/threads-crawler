from __future__ import annotations

import re
import urllib.parse as urlparse
from typing import Tuple

TRACKING_PARAMS = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","ref"}


def canonical_url(raw: str) -> str:
    try:
        u = urlparse.urlsplit(raw)
    except Exception:
        return raw
    scheme = u.scheme or "https"
    netloc = (u.netloc or "").lower()
    path = (u.path or "/").rstrip("/") or "/"

    # filter query params
    q = urlparse.parse_qsl(u.query, keep_blank_values=True)
    q = [(k, v) for (k, v) in q if k not in TRACKING_PARAMS]
    query = urlparse.urlencode(q, doseq=True)

    # drop fragment
    fragment = ""

    return urlparse.urlunsplit((scheme, netloc, path, query, fragment))


def normalize_text(s: str) -> str:
    # keep emojis, collapse spaces
    s = s.replace("\u00a0", " ")  # NBSP
    s = re.sub(r"[\t\r\f]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compute_recency_minutes(now_ts: float, item_ts: float) -> int:
    import math
    mins = int((now_ts - item_ts) / 60.0)
    return max(mins, 0)
