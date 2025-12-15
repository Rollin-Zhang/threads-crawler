from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class BatchHeaders:
    correlation_id: str
    idempotency_key: str


def make_batch(candidates: List[dict]) -> Tuple[dict, BatchHeaders]:
    """Pack candidates into a batch with correlation & idempotency.

    Idempotency-Key = sha1(sorted(candidate_ids))
    X-Correlation-Id = uuid4
    """
    ids = sorted([c.get("candidate_id", "") for c in candidates])
    idem = hashlib.sha1("|".join(ids).encode("utf-8")).hexdigest()
    corr = str(uuid.uuid4())
    payload = {"candidates": candidates}
    return payload, BatchHeaders(correlation_id=corr, idempotency_key=idem)
