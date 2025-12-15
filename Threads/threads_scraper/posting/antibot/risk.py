import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List


RUNS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "runs")
RUNS_DIR = os.path.abspath(RUNS_DIR)
os.makedirs(RUNS_DIR, exist_ok=True)


def _utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit_path(prefix: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(RUNS_DIR, f"{prefix}_{ts}.json")


def screenshot(page, name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(RUNS_DIR, f"{name}_{ts}.png")
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def audit_record(data: Dict[str, Any]) -> str:
    path = _audit_path("audit")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


class RiskLevel:
    NONE = "NONE"
    R1 = "R1"  # 輕微（429）
    R2 = "R2"  # 中度（403）
    R3 = "R3"  # 嚴重（挑戰/驗證）


def _visible_dialog_keywords(page: Any) -> Dict[str, Any]:
    """僅在可見對話框範圍內檢查高風險關鍵字，避免搜尋整頁造成誤報。
    回傳 {hits: [keyword...], text_sample: str}
    """
    try:
        data = page.evaluate(
            """
            () => {
              try {
                const isVisible = (el) => {
                  if (!el) return false;
                  const rect = el.getBoundingClientRect?.();
                  const style = window.getComputedStyle?.(el);
                  if (!rect) return false;
                  if (rect.width <= 1 || rect.height <= 1) return false;
                  if (style && (style.visibility === 'hidden' || style.display === 'none' || Number(style.opacity) === 0)) return false;
                  return true;
                };
                const dialogs = Array.from(document.querySelectorAll('div[role="dialog"], [aria-modal="true"]')).filter(isVisible);
                const bodyLike = dialogs.length ? dialogs : [document.body].filter(Boolean);
                const text = (el) => (el && (el.innerText || el.textContent) || '').toLowerCase();
                const txt = bodyLike.map(text).join('\n').slice(0, 4000);
                // 高風險關鍵字（可見對話框）
                const keywords = [
                  'captcha', 'verify', 'verification', 'checkpoint',
                  'unusual activity', 'suspicious', 'are you a human',
                  '驗證', '請完成驗證', '安全檢查', '挑戰', '機器人'
                ];
                const noise = [
                  'self-xss', 'media error', 'media_err', 'video error', 'audio error'
                ];
                const hits = keywords.filter(k => txt.includes(k)).filter(k => !noise.some(n => txt.includes(n)));
                return { hits, text_sample: txt.slice(0, 200) };
              } catch (e) { return { hits: [] }; }
            }
            """
        )
        return data if isinstance(data, dict) else {"hits": []}
    except Exception:
        return {"hits": []}


def _url_risk_indicators(page: Any, response: Optional[Any]) -> List[str]:
    """以 URL/端點判斷已知驗證或檢查頁面，回傳 triggers。"""
    triggers: List[str] = []
    try:
        url = None
        try:
            url = response.url if response else None
        except Exception:
            url = None
        page_url = None
        try:
            page_url = page.url
        except Exception:
            page_url = None
        urls = list(filter(None, [url, page_url]))
        allow = [
            'checkpoint', 'captcha', '/challenge/', '/security/', '/two_factor',
            'help/captcha', 'help/security'
        ]
        for u in urls:
            lu = str(u).lower()
            if any(a in lu for a in allow):
                triggers.append(f"url:{u}")
    except Exception:
        pass
    return triggers


def probe(response: Optional[Any], page: Any) -> Dict[str, Any]:
    # 回傳風險評估結果：{"level": RiskLevel.*, "reason": str, "triggers": [...]} 
    try:
        status = response.status if response else None
    except Exception:
        status = None

    triggers: List[str] = []
    if status == 429:
        triggers.append("http:429")
        return {"level": RiskLevel.R1, "reason": "HTTP 429", "triggers": triggers}
    if status == 403:
        triggers.append("http:403")
        return {"level": RiskLevel.R2, "reason": "HTTP 403", "triggers": triggers}

    # 僅在可見對話框內檢查高風險關鍵字
    try:
        vis = _visible_dialog_keywords(page)
        if isinstance(vis, dict) and vis.get("hits"):
            for h in vis.get("hits", [])[:5]:
                triggers.append(f"dialog:{h}")
    except Exception:
        pass

    # 以 URL/端點判斷
    try:
        triggers.extend(_url_risk_indicators(page, response))
    except Exception:
        pass

    if any(t.startswith("dialog:") for t in triggers) or any(t.startswith("url:") for t in triggers):
        return {"level": RiskLevel.R3, "reason": "dialog_or_url_indicator", "triggers": triggers}

    return {"level": RiskLevel.NONE, "reason": "ok", "triggers": triggers}


def handle(level: str, account_id: str, persona_id: str, page: Any) -> Dict[str, Any]:
    # 根據等級回傳處置建議與執行動作（截圖/記錄）
    if level == RiskLevel.R1:
        path = screenshot(page, "r1")
        return {"action": "backoff", "sleep": (60, 300), "screenshot": path}
    if level == RiskLevel.R2:
        path = screenshot(page, "r2")
        return {"action": "sleep", "sleep": (1800, 3600), "screenshot": path}
    if level == RiskLevel.R3:
        path = screenshot(page, "r3")
        incident = {
            "timestamp": _utc_now_iso(),
            "account_id": account_id,
            "persona_id": persona_id,
            "level": level,
            "screenshot": path,
        }
        with open(_audit_path("incident"), "w", encoding="utf-8") as f:
            json.dump(incident, f, ensure_ascii=False, indent=2)
        return {"action": "halt", "screenshot": path}
    return {"action": "continue"}


def summarize(level: str) -> Dict[str, Any]:
    """將風險等級轉成建議與提示（不含阻擋行為）。
    回傳 {"level": "R0|R1|R2|R3", "suggested_cooldown_s": N, "hints": [...]}。
    """
    if not level or level == RiskLevel.NONE:
        return {"level": "R0", "suggested_cooldown_s": 0, "hints": []}
    if level == RiskLevel.R1:
        return {"level": "R1", "suggested_cooldown_s": 600, "hints": ["429 Too Many Requests: 建議 5–15 分鐘降頻"]}
    if level == RiskLevel.R2:
        return {"level": "R2", "suggested_cooldown_s": 1800, "hints": ["403 Forbidden: 建議 15–45 分鐘冷卻與檢查環境"]}
    if level == RiskLevel.R3:
        return {"level": "R3", "suggested_cooldown_s": 3600, "hints": ["挑戰頁/驗證: 務必停止並改從官方 App 完成人驗證"]}
    return {"level": "R0", "suggested_cooldown_s": 0, "hints": []}
