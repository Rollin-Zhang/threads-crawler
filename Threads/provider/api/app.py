from __future__ import annotations

from flask import Flask, jsonify, request

from Threads.provider.common.config_loader import load_config
from Threads.provider.adapters.ingest import ingest
from Threads.provider.triage.persist import Store
from Threads.provider.triage.builder import build_candidates
from Threads.provider.triage.items_gate import ItemsGateConfig, ItemRule, apply_on_payload


def create_app(config_path: str = "config/triage_client.yaml") -> Flask:
    app = Flask(__name__)
    cfg = load_config(config_path)
    store = Store(cfg.persist_dir)

    @app.get("/status")
    def status():
        sent = len(store.read_jsonl("sent"))
        pending = len(store.read_jsonl("pending"))
        results = len(store.read_jsonl("results"))
        # dead_letter: list files in dead_letter dir
        import os
        dead_dir = os.path.join(store.base_dir, "dead_letter")
        dead_letter = 0
        try:
            dead_letter = len([f for f in os.listdir(dead_dir) if f.endswith('.json')])
        except Exception:
            pass

        # 聚合 items_gate 統計（從 sent.jsonl 彙總）
        ig_stats = {"stripped": {}, "skipped_records": 0, "warnings": []}
        try:
            for row in store.read_jsonl("sent"):
                ig = (row or {}).get("items_gate") or {}
                stripped = ig.get("stripped") or {}
                for k, v in stripped.items():
                    ig_stats["stripped"][k] = ig_stats["stripped"].get(k, 0) + int(v)
                ig_stats["skipped_records"] += int(ig.get("skipped_records") or 0)
                # warnings 聚合僅保留最新一批的內容以避免爆量
                if ig.get("warnings"):
                    ig_stats["warnings"] = ig.get("warnings")
        except Exception:
            pass
        return jsonify({
            "sent": sent,
            "pending": pending,
            "results": results,
            "dead_letter": dead_letter,
            "items_gate_stats": ig_stats,
        })

    @app.get("/triage/preview")
    def preview():
        limit = int(request.args.get("limit", 20))
        view = request.args.get("view", "record").lower()
        recs = ingest(cfg.data_dir)[:limit]
        if view == "candidate":
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
                sanitized, report, skip, _ = apply_on_payload(cd, ig_cfg, orig=rec.__dict__)
                if not skip:
                    out.append(sanitized)
            return jsonify(out)
        # default: original records
        return jsonify([r.__dict__ for r in recs])

    @app.get("/triage/sent")
    def sent_list():
        limit = int(request.args.get("limit", 50))
        rows = store.read_jsonl("sent")[-limit:]
        return jsonify(rows)

    @app.get("/triage/pending")
    def pending_list():
        limit = int(request.args.get("limit", 50))
        rows = store.read_jsonl("pending")[-limit:]
        return jsonify(rows)

    @app.get("/triage/results")
    def results_list():
        limit = int(request.args.get("limit", 50))
        rows = store.read_jsonl("results")[-limit:]
        return jsonify(rows)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=8081, debug=False)
