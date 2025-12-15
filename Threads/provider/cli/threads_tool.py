from __future__ import annotations

import argparse
import json
import os
from typing import List

from Threads.provider.common.config_loader import load_config
from Threads.provider.adapters.ingest import ingest
from Threads.provider.triage.gate0 import Gate0Config, run_gate0, summarize_reasons
from Threads.provider.triage.builder import build_candidates
from Threads.provider.triage.batcher import make_batch
from Threads.provider.triage.persist import Store
from Threads.provider.triage.client import post_batch
from Threads.provider.triage.fetcher import fetch_results
from Threads.provider.common.config_loader import get_auth_token
from Threads.provider.triage.items_gate import (
    ItemsGateConfig,
    ItemRule,
    apply_on_payload,
)


def _cmd_preview(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    data_dir = args.data_dir or cfg.data_dir
    recs = ingest(data_dir)[: args.limit]

    if getattr(args, "sanitized", False):
        # 構建候選並套用 Items Gate（payload_only）
        from Threads.provider.triage.builder import build_candidates
        from Threads.provider.triage.items_gate import ItemsGateConfig, ItemRule, apply_on_payload

        cands = build_candidates(recs, account_handle=cfg.account_handle, timezone=cfg.timezone)
        ig_cfg = ItemsGateConfig(
            enabled=cfg.items_gate_enabled,
            record_policy=cfg.items_gate_record_policy,
            default_mode=cfg.items_gate_default_mode,
            per_item={k: ItemRule(**v) if isinstance(v, dict) else ItemRule(mode=str(v)) for k, v in (cfg.items_gate_per_item or {}).items()},
            skip_if_any=cfg.items_gate_skip_if_any or [],
        )
        out = []
        for rec, cand in zip(recs, cands):
            cd = dict(cand.__dict__)
            sanitized, report, skip, reason = apply_on_payload(cd, ig_cfg, orig=rec.__dict__)
            if skip:
                item = {
                    "candidate_id": cd.get("candidate_id"),
                    "skipped": True,
                    "reason": reason,
                }
                if getattr(args, "include_report", False):
                    item["items_gate"] = {
                        "stripped": report.stripped,
                        "skipped_records": report.skipped_records,
                        "warnings": report.warnings,
                    }
                out.append(item)
            else:
                if getattr(args, "include_report", False):
                    sanitized = dict(sanitized)
                    sanitized["_items_gate"] = {
                        "stripped": report.stripped,
                        "skipped_records": report.skipped_records,
                        "warnings": report.warnings,
                    }
                out.append(sanitized)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 預設：僅顯示 ingest 的原始紀錄
    print(json.dumps([r.__dict__ for r in recs], ensure_ascii=False, indent=2))
    return 0


def _cmd_submit(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    store = Store(cfg.persist_dir)

    # ingest
    data_dir = args.data_dir or cfg.data_dir
    recs = ingest(data_dir)
    # gate0
    gcfg = Gate0Config(
        enabled=cfg.gate0_enabled,
        min_len=cfg.gate0_min_len,
        max_recency_minutes=cfg.gate0_max_recency_minutes,
        dedup_enabled=cfg.gate0_dedup_enabled,
        simhash_threshold=cfg.gate0_dedup_simhash_threshold,
        keywords_any=cfg.gate0_keywords_any,
    )
    gres = run_gate0(recs, gcfg)
    # build candidates
    cands = build_candidates(gres.accepted, account_handle=cfg.account_handle, timezone=cfg.timezone)
    # 若無候選，避免送出空批導致伺服器 400
    if not cands:
        summary = {
            "ok": True,
            "sent": 0,
            "gate0": {
                "total": len(recs),
                "accepted": len(gres.accepted),
                "rejected": len(gres.rejected),
                "reasons": summarize_reasons(gres),
            },
        }
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    # 決定執行模式（可由 CLI 覆寫）
    run_mode = (args.mode or cfg.batch_mode).lower()
    token = get_auth_token(cfg.auth_token_env)

    # Items Gate 配置（payload_only 路徑）
    ig_cfg = ItemsGateConfig(
        enabled=cfg.items_gate_enabled,
        record_policy=cfg.items_gate_record_policy,
        default_mode=cfg.items_gate_default_mode,
        per_item={k: ItemRule(**v) if isinstance(v, dict) else ItemRule(mode=str(v)) for k, v in (cfg.items_gate_per_item or {}).items()},
        skip_if_any=cfg.items_gate_skip_if_any or [],
    )
    total_items_gate = {"stripped": {}, "skipped_records": 0, "warnings": []}

    # 依 batch_max_size 分批送出
    cand_dicts = [c.__dict__ for c in cands]
    max_size = max(1, int(cfg.batch_max_size))
    total = len(cand_dicts)
    sent_batches = 0
    ok_batches = 0
    error_batches = 0
    for i in range(0, total, max_size):
        raw_batch = cand_dicts[i:i+max_size]
        # 應用 Items Gate（僅 payload 裝飾；id 仍來自 builder 原值）
        payload_batch = []
        ig_batch_stats = {"stripped": {}, "skipped_records": 0, "warnings": []}
        for cand in raw_batch:
            sanitized, report, skip, skip_reason = apply_on_payload(cand, ig_cfg)
            # 彙總批次統計
            for k, v in report.stripped.items():
                ig_batch_stats["stripped"][k] = ig_batch_stats["stripped"].get(k, 0) + v
            ig_batch_stats["skipped_records"] += report.skipped_records
            ig_batch_stats["warnings"].extend(report.warnings)
            if skip:
                # dead_letter 寫一筆簡短記錄
                store.append_dead_letter({
                    "candidate_hint": sanitized.get("candidate_id"),
                    "reason": skip_reason or "policy:items_gate_skip",
                })
                continue
            payload_batch.append(sanitized)

        # 累積到總統計
        for k, v in ig_batch_stats["stripped"].items():
            total_items_gate["stripped"][k] = total_items_gate["stripped"].get(k, 0) + v
        total_items_gate["skipped_records"] += ig_batch_stats["skipped_records"]
        total_items_gate["warnings"].extend(ig_batch_stats["warnings"])

        payload, headers = make_batch(payload_batch)
        # sent 記錄
        store.append_jsonl("sent", {
            "headers": {
                "X-Correlation-Id": headers.correlation_id,
                "Idempotency-Key": headers.idempotency_key,
            },
            "count": len(payload_batch),
            "items_gate": ig_batch_stats,
        })
        sent_batches += 1
        # 呼叫 PO_Bot，錯誤不終止整體流程
        try:
            resp = post_batch(
                base_url=cfg.http_base_url,
                token=token,
                payload=payload,
                correlation_id=headers.correlation_id,
                idempotency_key=headers.idempotency_key,
                mode=run_mode,
                wait_ms=cfg.batch_wait_ms,
                timeout=cfg.http_timeout_seconds,
                max_retries=cfg.http_max_retries,
                backoff_seconds=cfg.http_retry_backoff_seconds,
            )
        except Exception as e:
            error_batches += 1
            store.append_dead_letter({
                "error": "HTTP_ERROR",
                "message": str(e),
                "headers": {
                    "X-Correlation-Id": headers.correlation_id,
                    "Idempotency-Key": headers.idempotency_key,
                },
                "count": len(payload_batch),
            })
            continue
        # Persist response shards（支援多種鍵）
        store.append_jsonl("batch_resp", resp)
        ok_batches += 1
        # 1) 新版/替代格式：results
        for item in resp.get("results", []):
            store.append_jsonl("results", item)
        # 2) 舊版分段：done/skipped/errors/pending
        for item in resp.get("done", []):
            store.append_jsonl("results", item)
        for item in resp.get("skipped", []):
            store.append_jsonl("results", item)
        for item in resp.get("errors", []):
            store.append_dead_letter(item)
            store.append_jsonl("results", {"decision": "ERROR", **item})
        for p in resp.get("pending", []):
            store.append_jsonl("pending", p)

    print(json.dumps({
        "ok": error_batches == 0,
        "batches": {"sent": sent_batches, "ok": ok_batches, "error": error_batches},
        "total_candidates": total,
        "mode": run_mode,
        "items_gate": total_items_gate,
    }, ensure_ascii=False))
    return 0


def _cmd_poll(args: argparse.Namespace) -> int:
    import time as _time
    cfg = load_config(args.config)
    store = Store(cfg.persist_dir)
    token = get_auth_token(cfg.auth_token_env)

    interval = float(getattr(args, "interval", 3.0) or 3.0)
    max_iter = int(getattr(args, "max_iter", 1) or 1)
    until_empty = bool(getattr(args, "until_empty", False))

    iter_no = 0
    total_decided = 0
    while True:
        iter_no += 1
        rows = store.read_jsonl("pending")
        ids = [r.get("candidate_id") for r in rows if r.get("candidate_id")]
        if not ids:
            print(json.dumps({"ok": True, "pending": 0, "total_decided": total_decided}, ensure_ascii=False))
            break
        results = fetch_results(
            base_url=cfg.http_base_url,
            token=token,
            ids=ids,
            timeout=cfg.http_timeout_seconds,
            max_retries=cfg.http_max_retries,
            backoff_seconds=cfg.http_retry_backoff_seconds,
        )
        decided_ids = set([r.get("candidate_id") for r in results if r.get("candidate_id")])
        for r in results:
            store.append_jsonl("results", r)
        remain = [r for r in rows if r.get("candidate_id") not in decided_ids]
        store.replace_jsonl("pending", remain)
        total_decided += len(decided_ids)
        print(json.dumps({
            "ok": True, "iter": iter_no, "decided": len(decided_ids), "remain": len(remain), "total_decided": total_decided
        }, ensure_ascii=False))
        if not until_empty and iter_no >= max_iter:
            break
        if until_empty and not remain:
            break
        _time.sleep(max(0.1, interval))
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    store = Store(cfg.persist_dir)
    token = get_auth_token(cfg.auth_token_env)

    # 讀入 dead_letter 樣本並嘗試重送
    with open(args.file, "r", encoding="utf-8") as f:
        obj = json.load(f)
    # 允許是單筆 candidate 或整批 payload
    if "candidates" in obj:
        payload = obj
    else:
        payload = {"candidates": [obj]}
    from Threads.provider.triage.batcher import make_batch
    payload, headers = make_batch(payload["candidates"])  # 重新計算 idempotency/correlation
    resp = post_batch(
        base_url=cfg.http_base_url,
        token=token,
        payload=payload,
        correlation_id=headers.correlation_id,
        idempotency_key=headers.idempotency_key,
        mode=cfg.batch_mode,
        wait_ms=cfg.batch_wait_ms,
        timeout=cfg.http_timeout_seconds,
        max_retries=cfg.http_max_retries,
        backoff_seconds=cfg.http_retry_backoff_seconds,
    )
    print(json.dumps({"ok": True, "resp_keys": list(resp.keys())}, ensure_ascii=False))
    return 0


def main() -> int:
    p = argparse.ArgumentParser("threads_tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    p.add_argument("--config", default="config/triage_client.yaml")

    sp = sub.add_parser("triage-preview")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--data-dir", default=None, help="override data dir")
    sp.add_argument("--sanitized", action="store_true", help="apply Items Gate and show sanitized CandidateLite payloads")
    sp.add_argument("--include-report", action="store_true", help="include per-item items_gate report in output")
    sp.set_defaults(func=_cmd_preview)

    sp2 = sub.add_parser("triage-submit")
    sp2.add_argument("--data-dir", default=None, help="override data dir")
    sp2.add_argument("--mode", default=None, help="override batch mode: sync|async")
    sp2.set_defaults(func=_cmd_submit)

    sp3 = sub.add_parser("triage-poll")
    sp3.add_argument("--interval", type=float, default=3.0)
    sp3.add_argument("--max-iter", type=int, default=1)
    sp3.add_argument("--until-empty", action="store_true")
    sp3.set_defaults(func=_cmd_poll)

    sp4 = sub.add_parser("triage-replay")
    sp4.add_argument("--file", required=True)
    sp4.set_defaults(func=_cmd_replay)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
