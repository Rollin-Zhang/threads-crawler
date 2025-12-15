from __future__ import annotations

import time
from typing import Any, Dict, List

import requests


def _chunks(lst: List[str], n: int) -> List[List[str]]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def fetch_results(
    *,
    base_url: str,
    token: str | None,
    ids: List[str],
    timeout: int = 8,
    max_retries: int = 4,
    backoff_seconds: int = 2,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for group in _chunks(ids, 50):
        attempt = 1
        while True:
            url = f"{base_url}/triage/results?ids={','.join(group)}"
            headers: Dict[str, str] = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            try:
                resp = requests.get(url, headers=headers, timeout=timeout)
            except Exception:
                if attempt <= max_retries:
                    time.sleep(backoff_seconds * (2 ** (attempt - 1)))
                    attempt += 1
                    continue
                raise
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "1"))
                time.sleep(max(1, retry_after))
                continue
            if 500 <= resp.status_code < 600:
                if attempt <= max_retries:
                    time.sleep(backoff_seconds * (2 ** (attempt - 1)))
                    attempt += 1
                    continue
                resp.raise_for_status()
            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                raise RuntimeError("invalid json in results")
            if isinstance(data, list):
                out.extend(data)
            else:
                out.append(data)
            break
    return out
