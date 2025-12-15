from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Any, Dict

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class TriageConfig:
    data_dir: str
    timezone: str
    account_handle: str
    batch_mode: str
    batch_wait_ms: int
    batch_max_size: int
    batch_flush_seconds: int
    http_base_url: str
    http_timeout_seconds: int
    http_max_retries: int
    http_retry_backoff_seconds: int
    auth_token_env: str
    persist_dir: str
    gate0_enabled: bool
    gate0_min_len: int
    gate0_max_recency_minutes: int
    gate0_dedup_enabled: bool
    gate0_dedup_simhash_threshold: float
    gate0_keywords_any: list[str]
    # items gate
    items_gate_enabled: bool
    items_gate_record_policy: str
    items_gate_default_mode: str
    items_gate_per_item: Dict[str, Any]
    items_gate_skip_if_any: list[str]
    # context
    context_snippet_max_chars: int


def _read_yaml(path: str) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML not installed. Add 'pyyaml' to requirements.txt")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: str) -> TriageConfig:
    cfg = _read_yaml(path)
    source = cfg.get("source", {})
    account = cfg.get("account", {})
    batch = cfg.get("batch", {})
    http = cfg.get("http", {})
    security = cfg.get("security", {})
    persist = cfg.get("persist", {})
    gate0 = cfg.get("gate0", {})
    dedup = (gate0 or {}).get("dedup", {})
    items_gate = cfg.get("items_gate", {})
    context = cfg.get("context", {})

    return TriageConfig(
        data_dir=str(source.get("data_dir", "Threads/data")),
        timezone=str(source.get("timezone", "Asia/Taipei")),
        account_handle=str(account.get("handle", "")),
        batch_mode=str(batch.get("mode", "sync")),
        batch_wait_ms=int(batch.get("wait_ms", 1200)),
        batch_max_size=int(batch.get("max_size", 50)),
        batch_flush_seconds=int(batch.get("flush_seconds", 5)),
        http_base_url=str(http.get("base_url", "http://127.0.0.1:3000/v1")),
        http_timeout_seconds=int(http.get("timeout_seconds", 8)),
        http_max_retries=int(http.get("max_retries", 4)),
        http_retry_backoff_seconds=int(http.get("retry_backoff_seconds", 2)),
        auth_token_env=str(security.get("auth_token_env", "POBOT_TOKEN")),
        persist_dir=str(persist.get("dir", "Threads/provider/store")),
        gate0_enabled=bool(gate0.get("enabled", True)),
        gate0_min_len=int(gate0.get("min_len", 10)),
        gate0_max_recency_minutes=int(gate0.get("max_recency_minutes", 1440)),
        gate0_dedup_enabled=bool(dedup.get("enabled", True)),
        gate0_dedup_simhash_threshold=float(dedup.get("simhash_threshold", 0.92)),
        gate0_keywords_any=list(gate0.get("keywords_any", [])),
        items_gate_enabled=bool(items_gate.get("enabled", True)),
        items_gate_record_policy=str(items_gate.get("record_policy", "payload_only")),
        items_gate_default_mode=str(items_gate.get("default_mode", "strip")),
        items_gate_per_item=dict(items_gate.get("per_item", {
            "attachment": {"mode": "strip", "keep_alt": False, "max_chars": 0},
            "likes": {"mode": "strip"},
            "comments": {"mode": "strip"},
            "response_to": {"mode": "strip"},
            "author": {"mode": "strip"},
            "post_link": {"mode": "keep"},
            "datetime": {"mode": "keep"},
        })),
        items_gate_skip_if_any=list(items_gate.get("skip_if_any", [])),
        context_snippet_max_chars=int(context.get("snippet_max_chars", 500)),
    )


def get_auth_token(env_key: str) -> str | None:
    return os.environ.get(env_key)
