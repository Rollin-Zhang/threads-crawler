from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional


CRITICAL_FIELDS = {"content"}  # content 嚴禁攔截
ID_RELATED_FIELDS = {"post_link", "datetime"}  # 強烈建議 keep（防呆）
KNOWN_FIELDS = {"attachment", "likes", "comments", "response_to", "author", "post_link", "datetime", "content"}


@dataclass
class ItemRule:
    mode: str = "strip"  # strip | skip | keep
    keep_alt: bool = False  # 僅 attachment 用
    max_chars: int = 0  # >0 視為存在的下限


@dataclass
class ItemsGateConfig:
    enabled: bool
    record_policy: str  # "payload_only" | "record_and_payload"
    default_mode: str  # "strip" | "skip" | "keep"
    per_item: Dict[str, ItemRule]
    skip_if_any: List[str]


@dataclass
class ItemsGateReport:
    stripped: Dict[str, int]  # field -> count
    skipped_records: int
    warnings: List[str]


def _field_present(name: str, val: Any, rule: ItemRule) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        if not val.strip():
            return False
        if rule.max_chars and len(val) < rule.max_chars:
            return False
        return True
    # 數值/零值：只要不是 None 視為存在
    return True


def _to_rule(obj: Any, default_mode: str) -> ItemRule:
    if isinstance(obj, ItemRule):
        return obj
    if not isinstance(obj, dict):
        return ItemRule(mode=default_mode)
    mode = obj.get("mode", default_mode)
    keep_alt = bool(obj.get("keep_alt", False))
    max_chars = int(obj.get("max_chars", 0))
    return ItemRule(mode=mode, keep_alt=keep_alt, max_chars=max_chars)


def _get_value(candidate: dict, name: str, orig: Optional[dict] = None) -> Any:
    if name == "post_link":
        return candidate.get("seed", {}).get("value")
    if name == "author":
        return candidate.get("features", {}).get("author")
    if name == "likes":
        return candidate.get("features", {}).get("engagement", {}).get("likes")
    if name == "comments":
        return candidate.get("features", {}).get("engagement", {}).get("comments")
    if name == "content":
        return candidate.get("context_digest", {}).get("target_snippet")
    if name in ("attachment", "response_to", "datetime"):
        # CandidateLite 預設不含這些欄位；若提供 orig 則嘗試從原始紀錄讀取
        if orig is not None:
            return orig.get(name)
        return None
    return None


def _strip_field(candidate: dict, name: str) -> None:
    # 僅移除對應欄位；避免破壞其他必要結構
    if name == "post_link":
        # 移除 seed（可能使 schema 變嚴）
        if "seed" in candidate:
            candidate.pop("seed", None)
        return
    if name == "author":
        if "features" in candidate:
            candidate["features"].pop("author", None)
        return
    if name == "likes":
        if "features" in candidate and "engagement" in candidate["features"]:
            candidate["features"]["engagement"].pop("likes", None)
        return
    if name == "comments":
        if "features" in candidate and "engagement" in candidate["features"]:
            candidate["features"]["engagement"].pop("comments", None)
        return
    if name == "content":
        # 嚴禁 strip，外層會跳過
        return
    # attachment/response_to/datetime 預設不在 payload，無需處理
    return


def apply_on_payload(candidate: dict, cfg: ItemsGateConfig, orig: Optional[dict] = None) -> Tuple[dict, ItemsGateReport, bool, Optional[str]]:
    """
    回傳: (sanitized_candidate, report, skip_this_record, skip_reason)
    - 僅作用於送審的 CandidateLite（payload_only 路徑）
    - 不會修改 id/seed 來源（由外部 builder 以原始 StandardRecord 計算）
    """
    rep = ItemsGateReport(stripped={}, skipped_records=0, warnings=[])
    if not cfg.enabled:
        return candidate, rep, False, None

    # 防呆：若 per_item 包含 content，忽略 strip/skip 並警告
    if any(k in CRITICAL_FIELDS for k in cfg.per_item.keys()):
        # 只要出現 content 且非 keep，就告警
        rule = _to_rule(cfg.per_item.get("content", {}), cfg.default_mode)
        if rule.mode in ("strip", "skip"):
            rep.warnings.append("items_gate: 'content' cannot be stripped or skipped; forced keep.")

    # skip_if_any：若任一欄位存在且命中 -> 整筆 skip（僅針對已知欄位）
    for fname in cfg.skip_if_any:
        if fname in CRITICAL_FIELDS:
            rep.warnings.append(f"items_gate: '{fname}' is critical; skip_if_any entry ignored.")
            continue
        if fname not in KNOWN_FIELDS:
            continue
        rule = _to_rule(cfg.per_item.get(fname, {}), cfg.default_mode)
        cand_val = _get_value(candidate, fname, orig)
        if _field_present(fname, cand_val, rule):
            rep.skipped_records += 1
            return candidate, rep, True, f"policy:items_gate_skip:{fname}"

    sanitized = dict(candidate)
    # 僅針對已知欄位處理；未知欄位不動
    fields_to_consider = set(KNOWN_FIELDS)
    # 合併使用者有設定的欄位（若包含未知名稱則忽略）
    fields_to_consider |= set(k for k in (cfg.per_item or {}).keys() if k in KNOWN_FIELDS)
    fields_to_consider |= set(x for x in (cfg.skip_if_any or []) if x in KNOWN_FIELDS)

    for fname in sorted(fields_to_consider):
        # content 絕對不可動
        if fname in CRITICAL_FIELDS:
            continue
        rule = _to_rule(cfg.per_item.get(fname, {}), cfg.default_mode)
        m = rule.mode
        # id 相關欄位：若 strip/skip，視為移除對應 payload 欄位（不動 id 計算）
        if fname in ID_RELATED_FIELDS:
            # datetime 需保留，避免破壞 recency/posted_at；post_link 可從 payload 移除但不影響 id
            if fname == "datetime":
                if m in ("strip", "skip"):
                    rep.warnings.append("items_gate: 'datetime' cannot be stripped or skipped; forced keep.")
                continue
            if fname == "post_link" and m in ("strip", "skip"):
                _strip_field(sanitized, fname)
                rep.stripped[fname] = rep.stripped.get(fname, 0) + 1
                continue

        if m == "keep":
            continue
        cand_val = _get_value(sanitized, fname, orig)
        if not _field_present(fname, cand_val, rule):
            continue
        if m == "strip":
            _strip_field(sanitized, fname)
            rep.stripped[fname] = rep.stripped.get(fname, 0) + 1
        elif m == "skip":
            rep.skipped_records += 1
            return candidate, rep, True, f"policy:items_gate_skip:{fname}"

    return sanitized, rep, False, None
