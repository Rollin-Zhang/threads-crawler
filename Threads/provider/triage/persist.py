from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List


class Store:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, "dead_letter"), exist_ok=True)
        self.paths = {
            "sent": os.path.join(self.base_dir, "candidates_sent.jsonl"),
            "pending": os.path.join(self.base_dir, "pending.jsonl"),
            "results": os.path.join(self.base_dir, "triage_results.jsonl"),
            "batch_resp": os.path.join(self.base_dir, "batch_resp.jsonl"),
        }

    def append_jsonl(self, name: str, obj: Dict[str, Any]) -> None:
        fp = self.paths[name]
        with open(fp, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def append_dead_letter(self, obj: Dict[str, Any], *, filename: str | None = None) -> str:
        import time
        if not filename:
            filename = f"dead_{int(time.time()*1000)}.json"
        path = os.path.join(self.base_dir, "dead_letter", filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return path

    def read_jsonl(self, name: str) -> List[Dict[str, Any]]:
        fp = self.paths[name]
        out: List[Dict[str, Any]] = []
        if not os.path.exists(fp):
            return out
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
        return out

    def replace_jsonl(self, name: str, rows: List[Dict[str, Any]]) -> None:
        fp = self.paths[name]
        with open(fp, "w", encoding="utf-8") as f:
            for obj in rows:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
