from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from simhash import Simhash  # type: ignore

from Threads.provider.adapters.ingest import StandardRecord
from Threads.provider.adapters.normalize import normalize_text


@dataclass
class Gate0Config:
    enabled: bool
    min_len: int
    max_recency_minutes: int
    dedup_enabled: bool
    simhash_threshold: float
    keywords_any: List[str]


@dataclass
class Gate0Result:
    accepted: List[StandardRecord]
    rejected: List[Tuple[StandardRecord, str]]  # (record, reason)


def _simhash(s: str) -> int:
    return Simhash(s).value


def _hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def run_gate0(records: Iterable[StandardRecord], cfg: Gate0Config) -> Gate0Result:
    if not cfg.enabled:
        return Gate0Result(accepted=list(records), rejected=[])

    seen: List[int] = []  # simhash history
    accepted: List[StandardRecord] = []
    rejected: List[Tuple[StandardRecord, str]] = []

    now = time.time()

    for rec in records:
        text = normalize_text(rec.content)
        # keywords_any 可放寬長度
        min_len = 0 if any(kw in text for kw in cfg.keywords_any or []) else cfg.min_len
        if len(text) < min_len:
            rejected.append((rec, "policy:min_len"))
            continue
        # recency（若 datetime 解析失敗則放行，交由後續處理）
        try:
            import dateutil.parser  # type: ignore
            ts = dateutil.parser.isoparse(rec.datetime).timestamp()
            age_min = int((now - ts) / 60)
            if age_min > cfg.max_recency_minutes:
                rejected.append((rec, "policy:recency"))
                continue
        except Exception:
            pass
        # dedup by simhash
        if cfg.dedup_enabled:
            h = _simhash(text)
            is_dup = False
            for prev in seen:
                # simhash threshold 轉為相似度門檻（1-距離/64）
                dist = _hamming_distance(h, prev)
                similarity = 1.0 - (dist / 64.0)
                if similarity >= cfg.simhash_threshold:
                    is_dup = True
                    break
            if is_dup:
                rejected.append((rec, "policy:near_duplicate"))
                continue
            seen.append(h)

        accepted.append(rec)

    return Gate0Result(accepted=accepted, rejected=rejected)


def summarize_reasons(res: Gate0Result) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for _, reason in res.rejected:
        counts[reason] = counts.get(reason, 0) + 1
    return counts
