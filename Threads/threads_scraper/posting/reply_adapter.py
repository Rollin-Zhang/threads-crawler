from typing import Any, Dict, Optional
from .antibot.risk import probe as risk_probe, handle as risk_handle


_RANK = {"NONE": 0, "R0": 0, "R1": 1, "R2": 2, "R3": 3}


def _gtoe(a: Optional[str], b: Optional[str]) -> bool:
    try:
        return _RANK.get((a or "NONE").upper(), 0) >= _RANK.get((b or "R3").upper(), 3)
    except Exception:
        return False


def goto_thread(page: Any, url: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Navigate to the specific thread URL then risk probe once.
    Returns a dict with keys: {"risk": <risk_dict>, "url": final_url}
    """
    # normalize url by caller if needed; here assume already full URL
    to = int((cfg.get("timeouts", {}) or {}).get("goto_profile_ms", 3000))
    resp = page.goto(url, wait_until="domcontentloaded", timeout=to)
    try:
        page.wait_for_load_state("networkidle", timeout=min(2000, to))
    except Exception:
        pass
    # SPA hostname repin (threads.com -> threads.net)
    try:
        if bool((cfg.get("nav", {}) or {}).get("repin_after_spa", True)):
            page.evaluate(
                """
                (() => {
                  try {
                    const u = new URL(location.href);
                    if (u.hostname.endsWith('threads.com')) {
                      u.hostname = u.hostname.replace('threads.com', 'threads.net');
                      history.replaceState(null, '', u.toString());
                    }
                  } catch (e) {}
                })()
                """
            )
    except Exception:
        pass
    risk = risk_probe(resp, page)
    # enforce ceiling only when risk.mode=stop
    ceiling = ((cfg.get("risk", {}) or {}).get("ceiling"))
    mode = str(((cfg.get("risk", {}) or {}).get("mode", "warn"))).lower()
    if mode == "stop" and ceiling and _gtoe(risk.get("level"), ceiling):
        # immediate handle & let caller decide to abort
        action = risk_handle(risk.get("level"), "reply", "reply", page)
        return {"risk": risk, "url": page.url, "handled": action}
    return {"risk": risk, "url": page.url}


def trigger_reply_composer(page: Any, cfg: Dict[str, Any]) -> Optional[str]:
    """Find reply icon, click nearest button/role=button, wait composer, focus editor.
    Returns the editor selector used, or None on failure.
    """
    sel = (((cfg.get("reply", {}) or {}).get("selectors", {}) or {}).get("reply_icon_svg")) or ""
    fallbacks = [
        "svg[aria-label*='回覆' i]",
        "svg[aria-label*='Reply' i]",
    ]
    candidates = [s.strip() for s in (sel.split(',') if isinstance(sel, str) else []) if s.strip()] or fallbacks
    found = None
    for css in candidates:
        try:
            loc = page.locator(css)
            if loc and loc.count() > 0:
                found = loc.first
                break
        except Exception:
            continue
    if not found:
        return None
    # Try click closest button or role=button via XPath chain
    try:
        btn = found.locator("xpath=ancestor-or-self::button | xpath=ancestor-or-self::*[@role='button']").first
        btn.click(timeout=int((cfg.get("timeouts", {}) or {}).get("selector_ms", 1800)))
    except Exception:
        # final fallback: click svg directly
        try:
            found.click(timeout=int((cfg.get("timeouts", {}) or {}).get("selector_ms", 1800)))
        except Exception:
            return None
    # wait for composer open
    open_check = (((cfg.get("reply", {}) or {}).get("selectors", {}) or {}).get("composer_open_check")) or "div[contenteditable='true']"
    try:
        page.wait_for_selector(open_check, state="visible", timeout=int((cfg.get("timeouts", {}) or {}).get("selector_ms", 1800)))
    except Exception:
        return None
    # focus editor
    editor_sel = (((cfg.get("reply", {}) or {}).get("selectors", {}) or {}).get("editor_input")) or "div[contenteditable='true']"
    try:
        page.locator(editor_sel).first.click(timeout=int((cfg.get("timeouts", {}) or {}).get("selector_ms", 1800)))
        return editor_sel
    except Exception:
        return None
