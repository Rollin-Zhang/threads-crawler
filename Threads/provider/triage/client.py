from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

import requests


class HttpError(Exception):
    pass


def _sleep_backoff(base: int, attempt: int) -> None:
    time.sleep(base * (2 ** max(0, attempt - 1)))


def post_batch(
    *,
    base_url: str,
    token: str | None,
    payload: Dict[str, Any],
    correlation_id: str,
    idempotency_key: str,
    mode: str = "sync",
    wait_ms: int = 1200,
    timeout: int = 8,
    max_retries: int = 4,
    backoff_seconds: int = 2,
) -> Dict[str, Any]:
    url = f"{base_url}/triage/batch?mode={mode}&wait_ms={wait_ms}"
    headers = {
        "Content-Type": "application/json",
        "X-Correlation-Id": correlation_id,
        "Idempotency-Key": idempotency_key,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(1, max_retries + 2):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except Exception as e:
            if attempt <= max_retries:
                _sleep_backoff(backoff_seconds, attempt)
                continue
            raise HttpError(f"network error: {e}")

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "1"))
            time.sleep(max(1, retry_after))
            continue
        if 500 <= resp.status_code < 600:
            if attempt <= max_retries:
                _sleep_backoff(backoff_seconds, attempt)
                continue
            raise HttpError(f"server error {resp.status_code}: {resp.text}")
        if not (200 <= resp.status_code < 300):
            raise HttpError(f"http {resp.status_code}: {resp.text}")

        try:
            data = resp.json()
        except Exception:
            raise HttpError("invalid json response")
        # 這裡可接 schemas/triage_batch_resp.json 驗證（略過實作，交由後續）
        return data

    raise HttpError("unreachable")
