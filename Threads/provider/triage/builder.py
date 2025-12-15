from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Dict, List

from Threads.provider.adapters.ingest import StandardRecord
from Threads.provider.adapters.normalize import canonical_url, normalize_text
from Threads.provider.common.config_loader import load_config


@dataclass
class CandidateLite:
    platform: str
    account: Dict[str, str]
    seed: Dict[str, str]
    features: Dict[str, object]
    context_digest: Dict[str, str]
    submitted_at: str
    candidate_id: str


def _iso_now_tz(tz_name: str) -> str:
    import datetime, zoneinfo
    tz = zoneinfo.ZoneInfo(tz_name)
    return datetime.datetime.now(tz=tz).isoformat()


def _floor_to_minute(iso_str: str) -> str:
    # 將 ISO 字串截到分鐘粒度，便於 candidate_id 穩定
    from dateutil import parser
    dt = parser.isoparse(iso_str)
    dt = dt.replace(second=0, microsecond=0)
    return dt.isoformat()


def _to_utc_z(iso_str: str) -> str:
    """Normalize any ISO datetime string to UTC with 'Z' suffix."""
    from dateutil import parser, tz
    dt = parser.isoparse(iso_str)
    if dt.tzinfo is None:
        # assume input as UTC if naive
        dt = dt.replace(tzinfo=tz.UTC)
    dt_utc = dt.astimezone(tz.UTC)
    return dt_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_candidates(records: List[StandardRecord], *, account_handle: str, timezone: str) -> List[CandidateLite]:
    out: List[CandidateLite] = []
    now_iso = _iso_now_tz(timezone)
    # 讀取 config 以取得 snippet 長度上限（預設 500）
    try:
        cfg = load_config("config/triage_client.yaml")
        max_snippet = int(getattr(cfg, "context_snippet_max_chars", 500) or 500)
    except Exception:
        max_snippet = 500
    for r in records:
        url = canonical_url(r.post_link)
        content = normalize_text(r.content)
        # 產生 snippet 與審計欄位
        original_len = len(content)
        snippet = content[:max(0, max_snippet)]
        is_truncated = original_len > max_snippet

        # 正規化貼文時間為 UTC ISO（Z）
        try:
            posted_at_iso = _to_utc_z(r.datetime)
        except Exception:
            posted_at_iso = None

        # recency 以 posted_at_iso 與 now 計算；若解析失敗則 0
        try:
            from dateutil import parser
            base_dt = parser.isoparse(posted_at_iso) if posted_at_iso else parser.isoparse(now_iso)
            recency_minutes = int((parser.isoparse(now_iso).timestamp() - base_dt.timestamp())/60)
            if recency_minutes < 0:
                recency_minutes = 0
        except Exception:
            recency_minutes = 0
        features = {
            "lang": "zh-Hant",
            "author": r.author or "",
            "len": len(content),
            "engagement": {"likes": r.likes or 0, "comments": r.comments or 0},
            "recency_minutes": recency_minutes,
        }
        if posted_at_iso:
            features["posted_at_iso"] = posted_at_iso
        seed = {"type": "url", "value": url}
        context_digest = {
            "target_snippet": snippet,
            "original_len": original_len,
            "is_truncated": is_truncated,
        }
        # candidate_id = "CAND_" + sha1(canonical_url + sha1(content)[:16] + floor_to_minute(datetime))
        content_sha16 = hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]
        floor_dt = _floor_to_minute(r.datetime)
        basis = f"{url}{content_sha16}{floor_dt}"
        candidate_id = "CAND_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()

        cand = CandidateLite(
            platform="threads",
            account={"handle": account_handle},
            seed=seed,
            features=features,
            context_digest=context_digest,
            submitted_at=now_iso,
            candidate_id=candidate_id,
        )
        out.append(cand)
    return out
