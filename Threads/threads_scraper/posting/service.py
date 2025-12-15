import json
import os
from typing import Any, Dict, Optional
from ..auth.state_manager import storage_state_path
from ..auth.inherit import ensure_storage_state_from_cookies, verify_and_persist
from .selectors_registry import load_selectors
from .resolver import SelectorResolver
from .ui_actions import click, fill_rich_text, with_retry
from .confirm import confirm_posted
from .throttling import human_delay
from .antibot.behavior import warmup_page, hover_then_click, type_human
from .session_behavior import scroll_feed_random
from .antibot.persona import load_or_create_persona, save_persona
from .antibot.context_factory import create_context
from .antibot.risk import probe as risk_probe, handle as risk_handle, audit_record, summarize as risk_summarize
from .antibot.rate_limit import check as rl_check, update_counters as rl_update, update_last_risk as rl_update_risk
from .antibot.risk import RUNS_DIR as RUNS_DIR
from .selectors_registry import DEFAULT_CONFIG as DEFAULT_SELECTORS
from .antibot.publish_guard import arm_dom_neuter, arm_network_abort
from .antibot.cadence import recommend_cooldown
from .compose_text import (
    split_paragraphs,
    type_paragraphs,
    type_paragraphs_human_char,
    extract_editor_text,
    extract_editor_paragraphs_text,
    compare_text,
    try_fix_small_diff,
)
import uuid
import time
import random
from .reply_adapter import goto_thread as reply_goto_thread, trigger_reply_composer


class ErrorCodes:
    OK = 0
    NOT_LOGGED_IN = 10
    SELECTOR_MISSING = 20
    ACTION_FAILED = 30
    TIMEOUT = 40
    UNKNOWN = 99


def _is_logged_in(page: Any) -> bool:
    # 簡單檢測：存在 composer 或個人頭像等
    try:
        page.wait_for_selector("[contenteditable='true'], img[alt*='profile']", timeout=3000)
        return True
    except Exception:
        return False


def _normalize_profile_url(url_or_handle: Optional[str], handle: Optional[str]) -> Optional[str]:
    if url_or_handle:
        u = str(url_or_handle).strip()
        # normalize domain to threads.net
        u = u.replace("https://www.threads.com", "https://www.threads.net").replace("https://threads.com", "https://www.threads.net")
        if u.startswith("http"):
            # 附加語系參數（與 spider 對齊）
            if "?" not in u:
                u += "?hl=zh-tw"
            return u
        # fallthrough to handle path below
        handle = u
    if handle:
        h = handle.strip()
        if h.startswith("@"):
            h = h[1:]
        return f"https://www.threads.net/@{h}?hl=zh-tw"
    return None


def _is_composer_open(page: Any) -> bool:
    """Heuristic: composer is a dialog with contenteditable editor present."""
    try:
        dlg = page.locator("div[role='dialog']")
        if not dlg or dlg.count() == 0:
            return False
        ed = page.locator("div[role='dialog'] [contenteditable='true'], div[aria-modal='true'] [contenteditable='true']")
        return bool(ed and ed.count() > 0)
    except Exception:
        return False


def _attempt_close_composer(page: Any, verbose: bool = False, timeout_ms: int = 1200) -> bool:
    """Try to close the composer gently: Esc key, then common close/cancel buttons.
    Returns True if the composer seems closed.
    """
    try:
        if verbose:
            print("[post] try close composer: Esc")
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        try:
            page.wait_for_timeout(120)
        except Exception:
            pass
        if not _is_composer_open(page):
            return True
        # Try common close buttons/texts
        candidates = [
            "div[role='dialog'] button[aria-label*='關閉']",
            "div[role='dialog'] button[aria-label*='close' i]",
            "div[role='dialog'] [aria-label*='關閉']",
            "div[role='dialog'] [aria-label*='close' i]",
            "div[role='dialog'] button:has-text('取消')",
            "div[role='dialog'] button:has-text('Cancel')",
        ]
        for css in candidates:
            try:
                btn = page.locator(css)
                if btn and btn.count() > 0:
                    btn.first.click(timeout=timeout_ms)
                    try:
                        page.wait_for_timeout(100)
                    except Exception:
                        pass
                    if not _is_composer_open(page):
                        return True
            except Exception:
                continue
        # fallback: click outside dialog top-left corner
        try:
            box = page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
            if isinstance(box, dict) and box.get("w") and box.get("h"):
                page.mouse.click(10, 10)
                try:
                    page.wait_for_timeout(120)
                except Exception:
                    pass
        except Exception:
            pass
        return not _is_composer_open(page)
    except Exception:
        return False


# --- tiny helpers (in-file only, no behavior change) ---
def _safe_shot(page: Any, label: str, screenshots: Optional[list] = None) -> Optional[str]:
    """Best-effort screenshot; append into screenshots (if provided) and return path."""
    try:
        from .antibot.risk import screenshot as take_shot  # lazy import
        path = take_shot(page, label)
        try:
            if isinstance(screenshots, list) and isinstance(path, str):
                screenshots.append(path)
        except Exception:
            pass
        return path  # may be None
    except Exception:
        return None


def tl(timeline: list, step: str, **kwargs: Any) -> None:
    """Append a timeline entry. Keep original schema unchanged."""
    try:
        entry = {"step": step}
        if kwargs:
            entry.update(kwargs)
        timeline.append(entry)
    except Exception:
        # never block main flow
        pass


def _close_composer_safely(page: Any, verbose: bool = False, timeout_ms: int = 1200) -> tuple[bool, Optional[str]]:
    """Close composer using primary 'Cancel' buttons first, then ESC fallback.
    Returns (closed, method)."""
    composer_closed = False
    close_method: Optional[str] = None
    # primary: cancel buttons in dialog
    try:
        cancel_btns = [
            "div[role='dialog'] [role='button']:has-text('取消')",
            "div[role='dialog'] button:has-text('取消')",
            "div[role='dialog'] [role='button']:has-text('Cancel')",
            "div[role='dialog'] button:has-text('Cancel')",
        ]
        for css in cancel_btns:
            try:
                loc = page.locator(css)
                if loc and loc.count() > 0:
                    loc.first.click(timeout=timeout_ms)
                    try:
                        page.wait_for_timeout(120)
                    except Exception:
                        pass
                    if not _is_composer_open(page):
                        composer_closed = True
                        close_method = "cancel_click"
                        break
            except Exception:
                continue
    except Exception:
        pass
    # fallback: ESC helper
    if not composer_closed:
        if verbose:
            try:
                print("[post] try close composer: Esc")
            except Exception:
                pass
        composer_closed = _attempt_close_composer(page, verbose=verbose, timeout_ms=timeout_ms)
        if composer_closed and close_method is None:
            close_method = "esc_fallback"
    return composer_closed, close_method


def _open_home(context: Any, profile_url: Optional[str] = None):
    page = context.new_page()
    target = profile_url or "https://www.threads.net/?hl=zh-tw"
    resp = page.goto(target, wait_until="domcontentloaded")
    try:
        warmup_page(page)
    except Exception:
        pass
    return page, resp


def _new_context(p, persona: Dict[str, Any], storage_path: Optional[str], headless: bool):
    # 交由 context_factory 統一建立並注入 init scripts/headers
    return create_context(
        p,
        persona,
        storage_path,
        headless,
        skip_init_patches=False,
        enable_header_sanitize=True,
        enable_domain_pin=True,
    )


def post_new(
    content: str,
    headless: bool = True,
    selectors_path: Optional[str] = None,
    timeout_ms: int = 2500,
    dry_run: bool = False,
    retries: int = 1,
    verbose: bool = False,
    account_id: str = "default",
    sel_create: Optional[str] = None,
    sel_editor: Optional[str] = None,
    sel_publish: Optional[str] = None,
    rate_mode: str = "observe",
    run_mode: str = "rehearsal",
    ignore_risk_for_check: bool = False,
    min_interval_sec: Optional[int] = None,
    hour_cap: Optional[int] = None,
    day_cap: Optional[int] = None,
    profile_url: Optional[str] = None,
    profile_handle: Optional[str] = None,
    skip_init_patches: bool = False,
    disable_net_guard: bool = False,
    disable_domain_pin: bool = False,
    disable_header_sanitize: bool = False,
    humanize_session: Optional[str] = None,
    runtime_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # 預設 selectors.yaml
    selectors = load_selectors(selectors_path or DEFAULT_SELECTORS)
    # 覆寫 selectors（若 CLI 指定）
    if sel_create:
        selectors["compose_button"] = sel_create
    if sel_editor:
        selectors["composer_input"] = sel_editor
    if sel_publish:
        selectors["post_submit_button"] = sel_publish
    resolver = SelectorResolver(selectors)
    storage_path = storage_state_path()
    # 對齊 spider：若無 storage_state 但有 cookies，先嘗試轉檔
    storage_path = ensure_storage_state_from_cookies(logger=None)
    storage_exists = bool(storage_path and os.path.exists(storage_path))

    # Dry-run: 僅驗證選擇器與內容，完全不觸發 Playwright
    if dry_run:
        try:
            assert isinstance(content, str) and len(content.strip()) > 0, "content 為空"
            # 驗證必要 selectors 存在
            for k in ["compose_button", "composer_input", "post_submit_button"]:
                _ = resolver.get(k)
            return {"ok": True, "channel": "threads", "permalink": None, "timestamp": int(time.time()), "retries": retries, "artifacts": {"screenshots": []}, "error": None}
        except KeyError as e:
            return {"ok": False, "channel": "threads", "permalink": None, "timestamp": None, "retries": retries, "artifacts": {"screenshots": []}, "error": {"code": "SELECTOR_NOT_FOUND", "message": str(e)}}
        except Exception as e:
            return {"ok": False, "channel": "threads", "permalink": None, "timestamp": None, "retries": retries, "artifacts": {"screenshots": []}, "error": {"code": "UNEXPECTED", "message": str(e)}}

    try:
        # lazy import for environments lacking playwright during dry-run
        from playwright.sync_api import sync_playwright  # type: ignore
        with sync_playwright() as p:
            # 生成 request_id 並先寫一條 audit（避免重入）
            req_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
            timeline = []
            t_step = time.time()
            # 載入 rate limit 設定（預設 observe）
            try:
                limits_path = os.path.join(os.path.dirname(__file__), "config", "limits.yaml")
                cfg = None
                if os.path.exists(limits_path):
                    try:
                        import yaml  # type: ignore
                        with open(limits_path, "r", encoding="utf-8") as f:
                            cfg = yaml.safe_load(f) or {}
                    except Exception:
                        cfg = None
                cfg = cfg or {"mode": "observe", "min_interval_sec": 8, "hour_cap": 999, "day_cap": 9999}
            except Exception:
                cfg = {"mode": "observe", "min_interval_sec": 8, "hour_cap": 999, "day_cap": 9999}

            mode = (rate_mode or cfg.get("mode") or "observe").lower()
            mi = int(min_interval_sec if min_interval_sec is not None else cfg.get("min_interval_sec", 8))
            hc = int(hour_cap if hour_cap is not None else cfg.get("hour_cap", 999))
            dc = int(day_cap if day_cap is not None else cfg.get("day_cap", 9999))

            now_ts = time.time()
            # risk cooldown enforce wiring
            try:
                enforce_r3 = bool((cfg.get("risk", {}) or {}).get("enforce_cooldown_on_r3", False))
                cooldown_r3 = int((cfg.get("risk", {}) or {}).get("cooldown_on_r3_s", 3600))
            except Exception:
                enforce_r3, cooldown_r3 = (False, 3600)
            rl = rl_check(account_id=account_id, now_ts=now_ts, mode=mode, min_interval_sec=mi, hour_cap=hc, day_cap=dc, enforce_r3=enforce_r3, cooldown_on_r3_s=cooldown_r3)
            base_audit = {
                "timestamp": int(now_ts),
                "request_id": req_id,
                "account_id": account_id,
                "persona_id": f"{account_id}.json",
                "operation": "post_new",
                "rate": {
                    "mode": mode, "min_interval_sec": mi, "hour_cap": hc, "day_cap": dc,
                    "last_post_ts": rl["counters"]["last_post_ts"],
                    "hour_count": rl["counters"]["hour_count"],
                    "day_count": rl["counters"]["day_count"],
                    "reason": rl["reason"],
                    "next_try_eta": rl.get("next_try_eta"),
                },
            }
            audit_record({**base_audit, "result": "start", "warnings": ([f"rate_warn:{rl['reason']}"] if (mode in ("off","observe") and rl['reason'] != 'ok') else [])})

            if mode == "enforce" and not rl.get("allowed", True):
                audit_record({**base_audit, "result": "blocked", "error": {"code": "RATE_LIMIT", "message": rl["reason"], "details": {"reason": rl["reason"], "next_try_eta": rl.get("next_try_eta")}}})
                return {
                    "ok": False,
                    "channel": "threads",
                    "permalink": None,
                    "timestamp": None,
                    "retries": retries,
                    "artifacts": {"screenshots": []},
                    "error": {"code": "RATE_LIMIT", "message": rl["reason"], "details": {"reason": rl["reason"], "next_try_eta": rl.get("next_try_eta")}},
                }

            # Persona：固定優先，週期微幅輪替
            persona = load_or_create_persona(account_id=account_id, ttl_days=7, mode="sticky")
            save_persona(account_id, persona)  # 確保落盤
            enable_domain_pin = not bool(disable_domain_pin)
            enable_header_sanitize = not bool(disable_header_sanitize)
            # 建立 context（可切換網路攔截器與 init patches）
            browser, ctx = create_context(
                p,
                persona,
                storage_path,
                headless,
                skip_init_patches=False,
                enable_header_sanitize=enable_header_sanitize,
                enable_domain_pin=enable_domain_pin,
            )
            # 重新建立 context 以支援 skip_init_patches 開關
            if skip_init_patches:
                try:
                    browser.close()
                except Exception:
                    pass
                browser, ctx = create_context(
                    p,
                    persona,
                    storage_path,
                    headless,
                    skip_init_patches=True,
                    enable_header_sanitize=enable_header_sanitize,
                    enable_domain_pin=enable_domain_pin,
                )
            # 啟用 tracing（可選）
            try:
                ctx.tracing.start(screenshots=True, snapshots=True)
            except Exception:
                pass
            # 建立 page 並在 verbose 下加強診斷
            page = ctx.new_page()
            try:
                # 降低預設動作 timeout，避免單次動作卡 30s
                page.set_default_timeout(2500)
                page.set_default_navigation_timeout(4000)
            except Exception:
                pass
            if verbose:
                try:
                    def _on_console(msg):
                        try:
                            t = None
                            try:
                                t = msg.type() if callable(getattr(msg, 'type', None)) else getattr(msg, 'type', None)
                            except Exception:
                                t = None
                            text = None
                            try:
                                text = msg.text() if callable(getattr(msg, 'text', None)) else str(msg)
                            except Exception:
                                text = "<unreadable>"
                            # 噪音過濾：常見非致命 MEDIA_ERR 與 progressive js 提示
                            low = (text or "").lower()
                            if any(kw in low for kw in ["media_err_src_not_supported", "media error", "progressive_javascript_native", "subsequent non-fatal errors won't be logged"]):
                                return
                            print(f"[console:{t}] {text}")
                        except Exception:
                            # 保底，避免事件處理器再噴錯
                            print("[console:<err>] handler error")

                    def _on_pageerror(err):
                        try:
                            print("[pageerror]", err)
                        except Exception:
                            print("[pageerror] <unreadable>")

                    def _on_requestfailed(req):
                        try:
                            failure = None
                            try:
                                failure = req.failure
                            except Exception:
                                failure = None
                            err_text = None
                            if failure:
                                try:
                                    err_text = failure.get("errorText") if isinstance(failure, dict) else getattr(failure, "error_text", None)
                                except Exception:
                                    err_text = None
                            # Suppress common noisy failures under dress mode (media/cdn/graphql) and non-critical subresources
                            try:
                                url = req.url if hasattr(req, 'url') else None
                            except Exception:
                                url = None
                            rtype = None
                            try:
                                rtype = req.resource_type if hasattr(req, 'resource_type') else None
                            except Exception:
                                rtype = None
                            low_url = (url or "").lower()
                            noisy_domains = (".cdninstagram.com", ".fbcdn.net", ".cdn-ig", "ig-cdn",
                                             "video", "image", "scontent")
                            noisy_paths = ("/graphql/", "/api/graphql", "/logging_client_events", "/events", "/favicon")
                            # Treat these resource types as low-signal
                            low_signal_types = ("image", "media", "stylesheet", "font")
                            is_noisy = False
                            try:
                                if any(d in low_url for d in noisy_domains):
                                    is_noisy = True
                                if any(p in low_url for p in noisy_paths):
                                    is_noisy = True
                                if rtype in low_signal_types:
                                    is_noisy = True
                            except Exception:
                                pass
                            # In dress mode, GraphQL/script may be aborted intentionally; filter them if clearly Threads-owned and benign
                            if not is_noisy:
                                print("[reqfail]", url or "<no-url>", err_text or "")
                        except Exception:
                            print("[reqfail] <handler error>")

                    def _resp_logger(resp):
                        try:
                            rt = None
                            try:
                                rt = resp.request.resource_type
                            except Exception:
                                rt = None
                            st = None
                            try:
                                st = resp.status
                            except Exception:
                                st = None
                            if rt in ("document", "script") and (st is not None) and st >= 400:
                                print("[resp>=400]", st, rt, resp.url)
                        except Exception:
                            pass

                    page.on("console", _on_console)
                    page.on("pageerror", _on_pageerror)
                    page.on("requestfailed", _on_requestfailed)
                    page.on("response", _resp_logger)
                except Exception:
                    pass

            # Preflight：確認 domain 可回應（避免 DNS/redirect 問題誤導）
            try:
                page.goto("https://www.threads.net/robots.txt", wait_until="domcontentloaded", timeout=1500)
            except Exception:
                pass

            # 先到首頁 → 驗證登入並保存（對齊 spider）
            home = "https://www.threads.net/?hl=zh-tw"
            if verbose:
                print("[goto] home:", home)
            t0 = time.time()
            # runtime cfg for timeouts available later; use a safe short default for first goto
            resp = page.goto(home, wait_until="domcontentloaded", timeout=3000)
            tl(timeline, "goto_home", ms=int((time.time()-t0)*1000))
            try:
                page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass

            # 驗證並保存會話（與 spider 一致）
            logged_in_ok = False
            try:
                if not (run_mode == "check" and ignore_risk_for_check):
                    logged_in_ok = verify_and_persist(page, logger=None)
            except Exception:
                logged_in_ok = False

            # 風險探測（首頁載入後）：R1/R2（非 live）不中斷僅警告；live 且 risk_mode=stop 則早停；R3 非 check 早停
            risk = risk_probe(resp, page)
            risk_summary = risk_summarize(risk.get("level")) if risk else {"level": "R0", "suggested_cooldown_s": 0, "hints": []}
            risk_warnings: list[dict] = []
            # 持久化最後風險（僅在非 NONE 時）
            try:
                if risk and risk.get("level") in ("R1","R2","R3"):
                    rl_update_risk(account_id, risk.get("level"), time.time())
            except Exception:
                pass
            if risk.get("level") in ("R1", "R2"):
                if run_mode == "live" and str(cfg.get("risk", {}).get("mode", "warn")).lower() == "stop":
                    action = risk_handle(risk.get("level"), account_id, account_id, page)
                    audit_record({
                        "timestamp": int(time.time()),
                        "account_id": account_id,
                        "persona_id": f"{account_id}.json",
                        "operation": "open_home",
                        "result": "risk",
                        "error": {"code": "RATE_LIMIT" if risk["level"] == "R1" else "FORBIDDEN", "message": f"risk:{risk['level']}"},
                        "screenshots": [action.get("screenshot")] if isinstance(action.get("screenshot"), str) else [],
                        "warnings": [f"risk:{risk['level']}:home"],
                    })
                    trace_path = None
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    browser.close()
                    return {
                        "ok": False,
                        "channel": "threads",
                        "permalink": None,
                        "timestamp": None,
                        "retries": retries,
                        "artifacts": {"screenshots": [action.get("screenshot")] if isinstance(action.get("screenshot"), str) else [], "trace": trace_path},
                        "error": {"code": "RATE_LIMIT" if risk["level"] == "R1" else "FORBIDDEN", "message": f"risk:{risk['level']}"},
                        "risk_summary": risk_summary,
                        "risk_triggers": risk.get("triggers", []),
                        "risk_warnings": [f"risk:{risk['level']}:home"],
                        "timeline": timeline,
                    }
                else:
                    # 非 live：不中斷、僅警告
                    risk_warnings.append({"stage": "home", "level": risk.get("level")})
                    audit_record({**base_audit, "result": "warn", "warnings": [f"risk:{risk['level']}:home"]})

            if risk.get("level") == "R3" and not (run_mode == "check" and ignore_risk_for_check) and not logged_in_ok:
                try:
                    alt = home
                    page.goto(alt, wait_until="domcontentloaded")
                    logged_in_ok = verify_and_persist(page, logger=None)
                    risk2 = risk_probe(None, page)
                except Exception:
                    risk2 = risk
                if risk2.get("level") == "R3" and not logged_in_ok:
                    try:
                        rl_update_risk(account_id, "R3", time.time())
                    except Exception:
                        pass
                    action = risk_handle(risk2.get("level"), account_id, account_id, page)
                    audit_record({
                        "timestamp": int(time.time()),
                        "account_id": account_id,
                        "persona_id": f"{account_id}.json",
                        "operation": "open_home",
                        "result": "risk",
                        "error": {"code": "CHALLENGE_DETECTED", "message": f"risk:{risk2['level']}"},
                        "screenshots": [action.get("screenshot")] if isinstance(action.get("screenshot"), str) else [],
                        "warnings": [f"risk:{risk2['level']}:home"],
                    })
                    trace_path = None
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    browser.close()
                    return {
                        "ok": False,
                        "channel": "threads",
                        "permalink": None,
                        "timestamp": None,
                        "retries": retries,
                        "artifacts": {"screenshots": [action.get("screenshot")] if isinstance(action.get("screenshot"), str) else [], "trace": trace_path},
                        "error": {"code": "CHALLENGE_DETECTED", "message": f"risk:{risk2['level']}"},
                        "risk_summary": risk_summarize(risk2.get("level")),
                        "risk_triggers": risk2.get("triggers", []),
                        "risk_warnings": [f"risk:{risk2['level']}:home"],
                        "timeline": timeline,
                    }

            # 若提供 profile，導向個人頁（確保使用 .net + ?hl=zh-tw）
            # Humanize pre-browse（check 預設 off，其他模式預設 on）
            humanize_on = False
            # runtime config
            try:
                from .config.loader import load_runtime_cfg
                cfg = load_runtime_cfg(overrides=(runtime_overrides or {}))
            except Exception:
                cfg = {"humanize": {"pre_feed_seconds": (60,90), "post_feed_seconds": (30,60), "scroll_step_px": (180,420), "scroll_pause_ms": (120,360), "micro_mouse": True}, "risk": {"mode": "warn", "stop_on_r3_live": True}}
            # apply timeouts from cfg when available
            try:
                sel_to = int(cfg.get("timeouts", {}).get("selector_ms", 1800))
            except Exception:
                sel_to = 1800
            if run_mode == "check":
                humanize_on = (str(humanize_session).lower() == "on")
            else:
                humanize_on = (str(humanize_session).lower() != "off") if humanize_session is not None else True
            # module toggles from cfg (defaults: enabled)
            try:
                enable_scroll = bool(cfg.get("modules", {}).get("scroll", True))
                enable_composer = bool(cfg.get("modules", {}).get("composer", True))
                enable_typing = bool(cfg.get("modules", {}).get("typing", True))
            except Exception:
                enable_scroll = True
                enable_composer = True
                enable_typing = True
            # typing speed and para extraction css
            try:
                per_char_rng = cfg.get("typing", {}).get("per_char_ms", (600, 1200))
                para_css = cfg.get("typing", {}).get("para_selector", "p[class]")
            except Exception:
                per_char_rng = (600, 1200)
                para_css = "p[class]"
            if humanize_on:
                try:
                    t0 = time.time()
                    pre = None
                    if enable_scroll:
                        # 可選：先抑制媒體噪音
                        try:
                            if bool(cfg.get("nav", {}).get("suppress_media", False)):
                                page.add_init_script(
                                    """
                                    (()=>{try{const stop=()=>{document.querySelectorAll('video, audio').forEach(m=>{try{m.muted=true;m.pause();}catch(e){}})};stop();document.addEventListener('visibilitychange',stop,true);}catch(e){}})();
                                    """
                                )
                        except Exception:
                            pass
                        # 關閉 composer 模組時：硬闆阻擋 editor 類互動（click/focus/keypress）
                        try:
                            if not enable_composer:
                                page.add_init_script(
                                    """
                                    (function(){
                                      try{
                                        const isBad = el => {
                                          if(!el) return false;
                                          const role = (el.getAttribute && el.getAttribute('role'))||'';
                                          const ce = (el.getAttribute && el.getAttribute('contenteditable'))||'';
                                          const ph = (el.getAttribute && el.getAttribute('placeholder'))||'';
                                          const css = (sel)=>el.matches?el.matches(sel):false;
                                          return css('[contenteditable="true"]') || (role==='textbox' && ce==='true') || /建立串文|create thread/i.test(ph);
                                        };
                                        const h = (ev)=>{
                                          try{const t=ev.target; if(isBad(t)||isBad(t.closest? t.closest('*[contenteditable="true"], [role="textbox"], textarea') : null)){ev.stopImmediatePropagation(); ev.stopPropagation(); ev.preventDefault();}}catch(e){}
                                        };
                                        ['click','mousedown','mouseup','focus','keydown','keypress','keyup'].forEach(evt=>{
                                          document.addEventListener(evt, h, true);
                                        });
                                      }catch(e){}
                                    })();
                                    """
                                )
                        except Exception:
                            pass
                        pre = scroll_feed_random(
                            page,
                            seconds_rng=cfg["humanize"]["pre_feed_seconds"],
                            step_px_rng=cfg["humanize"]["scroll_step_px"],
                            pause_ms_rng=cfg["humanize"]["scroll_pause_ms"],
                            micro_mouse=cfg["humanize"].get("micro_mouse", True),
                            max_steps=int(runtime_overrides.get("max_pre_steps")) if isinstance(runtime_overrides, dict) and runtime_overrides.get("max_pre_steps") is not None else None,
                            initial_idle_rng=cfg["humanize"].get("initial_idle_seconds"),
                        )
                        tl(timeline, "pre_scroll", ms=int((time.time()-t0)*1000))
                except Exception:
                    pre = {"duration_s": 0, "steps": 0}
            else:
                pre = None

            target_profile = _normalize_profile_url(profile_url, profile_handle)
            if target_profile:
                if verbose:
                    print("[goto] profile:", target_profile)
                t0 = time.time()
                try:
                    to_prof = int(cfg.get("timeouts", {}).get("goto_profile_ms", 3000))
                except Exception:
                    to_prof = 3000
                page.goto(target_profile, wait_until="domcontentloaded", timeout=to_prof)
                tl(timeline, "goto_profile", ms=int((time.time()-t0)*1000))
                try:
                    page.wait_for_load_state("networkidle", timeout=min(2000, to_prof))
                except Exception:
                    pass

                # 有些情境下（前端 SPA pushState），網址可能被改回 threads.com，這裡以 replaceState 無痕釘回 threads.net
                try:
                    if bool(cfg.get("nav", {}).get("repin_after_spa", True)):
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

                # 如果這次是 reply 流（透過 run_reply_flow 傳入 permalink 到 profile_url），
                # 我們希望在 thread 頁面上不要執行 pre-scroll 模擬，以便立即點擊回覆與輸入。
                # 這裡以 runtime_overrides 的旗標允許精準控制，預設 reply flow 已設定該旗標。
                try:
                    if isinstance(runtime_overrides, dict) and runtime_overrides.get("skip_thread_pre_scroll"):
                        tl(timeline, "pre_scroll_skipped", reason="reply_flow")
                    else:
                        # 非 reply 流仍可在抵達後進行少量暖場（維持原行為）。
                        pass
                except Exception:
                    pass

                # Hydration / Spinner Watchdog：抓空白/殼層狀態並重試一次
                try:
                    snap = page.evaluate("""(() => { const body=document.body; const txtLen=body?body.innerText.trim().length:0; const hasRoot=!!document.querySelector('div.x78zum5.xdt5ytf'); return {href:location.href, ready:document.readyState, txtLen, hasRoot}; })()""")
                    if verbose:
                        print("[snap0]", snap)
                except Exception:
                    snap = {"error": True}
                try:
                    if (not snap.get("hasRoot")) and int(snap.get("txtLen", 0)) < 20:
                        if verbose:
                            print("[goto] looks blank/spinner → retry once")
                        page.goto(target_profile, wait_until="domcontentloaded", timeout=3000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=2000)
                        except Exception:
                            pass
                        try:
                            snap2 = page.evaluate("""(() => { const body=document.body; const txtLen=body?body.innerText.trim().length:0; const hasRoot=!!document.querySelector('div.x78zum5.xdt5ytf'); return {href:location.href, ready:document.readyState, txtLen, hasRoot}; })()""")
                            if verbose:
                                print("[snap1]", snap2)
                        except Exception:
                            pass
                except Exception:
                    pass

                # 導航後截圖
                _safe_shot(page, "goto_after_dom")


            # 若仍無法確認登入，且非 check(ignore) 模式，直接回報未登入
            if not (run_mode == "check" and ignore_risk_for_check):
                if not logged_in_ok:
                    try:
                        ctx.tracing.stop(path=os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip"))
                    except Exception:
                        pass
                    browser.close()
                    return {"ok": False, "code": ErrorCodes.NOT_LOGGED_IN, "message": "not logged in"}

            # run-mode: check（不開 composer，不輸入）→ 改為「軟診斷」，不丟錯
            if run_mode == "check":
                screenshots = []
                # 診斷探測器：不丟錯，返回 syntax_ok / present / visible
                def _probe(css: str, to: int = 1500) -> Dict[str, Any]:
                    d = {"syntax_ok": True, "present": False, "visible": False}
                    try:
                        loc = page.locator(css)
                        cnt = loc.count()
                        d["present"] = (cnt and cnt > 0)
                        if d["present"]:
                            try:
                                loc.first.wait_for(state="visible", timeout=to)
                                d["visible"] = True
                            except Exception:
                                pass
                    except Exception:
                        d["syntax_ok"] = False
                    return d

                selector_diagnostics: Dict[str, Any] = {}
                for k, alias in [("compose_button","create_entry"),("composer_input","editor"),("post_submit_button","publish_button")]:
                    # 聚合多個候選成單一診斷：有任一候選 visible 即視為 visible
                    parts = resolver.get_all(k)
                    merged = {"syntax_ok": False, "present": False, "visible": False}
                    for css in parts:
                        res = _probe(css)
                        merged["syntax_ok"] = merged["syntax_ok"] or res["syntax_ok"]
                        merged["present"] = merged["present"] or res["present"]
                        merged["visible"] = merged["visible"] or res["visible"]
                    selector_diagnostics[alias] = merged
                # 截圖
                _safe_shot(page, "check_home", screenshots)
                trace_path = None
                try:
                    trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                    ctx.tracing.stop(path=trace_path)
                except Exception:
                    pass
                audit_record({
                    "timestamp": int(time.time()),
                    "account_id": account_id,
                    "persona_id": f"{account_id}.json",
                    "operation": "post_new",
                    "result": "checked",
                    "run_mode": run_mode,
                    "screenshots": screenshots,
                    "risk_ignored": bool(ignore_risk_for_check),
                    "trace": trace_path,
                    "selectors_checked": ["create_entry","editor","publish_button"],
                    "selector_diagnostics": selector_diagnostics,
                })
                browser.close()
                return {
                    "ok": True,
                    "channel": "threads",
                    "checked": ["create_entry","editor","publish_button"],
                    "timestamp": int(time.time()),
                    "retries": retries,
                    "artifacts": {"screenshots": screenshots, "trace": trace_path},
                    "run_mode": run_mode,
                    "risk_ignored": bool(ignore_risk_for_check),
                    "selector_diagnostics": selector_diagnostics,
                    "humanize": (pre if pre else None),
                    "risk_summary": risk_summary,
                    "risk_triggers": risk.get("triggers", []),
                    "timeline": timeline,
                    "cfg": {"modules": cfg.get("modules", {}), "humanize": cfg.get("humanize", {}), "timeouts": cfg.get("timeouts", {})},
                    "error": None,
                }

            # 提早結束：當關閉 composer 模組時（例如只想做 pre-scroll 和風險檢查）
            if not enable_composer:
                # DOM challenge detector: restrict to visible dialog scope to reduce false positives
                try:
                    dom_risk = page.evaluate(
                        """
                        () => {
                          try {
                            const isVisible = (el) => {
                              if (!el) return false;
                              const r = el.getBoundingClientRect?.();
                              const st = window.getComputedStyle?.(el);
                              if (!r) return false;
                              if (r.width <= 1 || r.height <= 1) return false;
                              if (st && (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) === 0)) return false;
                              return true;
                            };
                            const dialogs = Array.from(document.querySelectorAll('div[role="dialog"], [aria-modal="true"]')).filter(isVisible);
                            const areas = dialogs.length ? dialogs : [document.body].filter(Boolean);
                            const txt = areas.map(el => (el.innerText||'').toLowerCase()).join('\n');
                            const hit = /captcha|verify|checkpoint|安全檢查|驗證/.test(txt);
                            return {hit, sample: txt.slice(0, 200)};
                          } catch (e) { return {hit: false}; }
                        }
                        """
                    )
                except Exception:
                    dom_risk = {"hit": False}
                # risk ceiling enforcement
                ceiling = (cfg.get("risk", {}) or {}).get("ceiling")
                if dom_risk and dom_risk.get("hit") and ceiling in ("R1","R2"):
                    tl(timeline, "dom_risk_hit", details={"ceiling": ceiling})
                    trace_path = None
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    browser.close()
                    return {
                        "ok": True,
                        "channel": "threads",
                        "permalink": None,
                        "timestamp": int(time.time()),
                        "retries": retries,
                        "artifacts": {"screenshots": [], "trace": trace_path},
                        "simulated_publish": True,
                        "run_mode": run_mode,
                        "humanize": {"pre_s": (pre or {}).get("duration_s"), "post_s": None, "steps": (pre or {}).get("steps")},
                        "risk_summary": risk_summary,
                        "risk_triggers": risk.get("triggers", []),
                        "risk_warnings": ["dom_risk_hit"],
                        "timeline": timeline,
                        "modules": {"scroll": enable_scroll, "composer": enable_composer, "typing": enable_typing},
                        "cfg": {"modules": cfg.get("modules", {}), "humanize": cfg.get("humanize", {}), "timeouts": cfg.get("timeouts", {}), "risk": {k: cfg.get("risk", {}).get(k) for k in ("mode","ceiling")}},
                        "composer_closed": True,
                        "text_check": None,
                        "error": None,
                    }
                # cadence 建議
                now_ts_ps = time.time()
                cd_ps = recommend_cooldown(now_ts_ps, rl.get("counters", {}).get("last_post_ts"), {"min_interval_sec": mi, "hour_cap": hc, "day_cap": dc})
                cadence_warnings_ps = []
                if cd_ps and cd_ps.get("suggested_sleep_s", 0) > 0:
                    cadence_warnings_ps.append({"reason": cd_ps.get("reason"), "suggested_sleep_s": cd_ps.get("suggested_sleep_s")})
                trace_path = None
                try:
                    trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                    ctx.tracing.stop(path=trace_path)
                except Exception:
                    pass
                browser.close()
                return {
                    "ok": True,
                    "channel": "threads",
                    "permalink": None,
                    "timestamp": int(time.time()),
                    "retries": retries,
                    "artifacts": {"screenshots": [], "trace": trace_path},
                    "simulated_publish": True,
                    "run_mode": run_mode,
                    "humanize": {"pre_s": (pre or {}).get("duration_s"), "post_s": None, "steps": (pre or {}).get("steps")},
                    "risk_summary": risk_summary,
                    "risk_triggers": risk.get("triggers", []),
                    "cadence_warnings": cadence_warnings_ps,
                    "cooldown_recommendation": (cd_ps or {}).get("suggested_sleep_s", 0),
                    "timeline": timeline,
                    "modules": {"scroll": enable_scroll, "composer": enable_composer, "typing": enable_typing},
                    "cfg": {"modules": cfg.get("modules", {}), "humanize": cfg.get("humanize", {}), "timeouts": cfg.get("timeouts", {}), "risk": {k: cfg.get("risk", {}).get(k) for k in ("mode","ceiling")}},
                    "composer_closed": True,
                    "text_check": None,
                    "error": None,
                }

            # 進入 composer（rehearsal/dress/live）
            screenshots = []
            permalink = None
            try:
                # 風險 Gate #1：開啟 composer 之前
                try:
                    risk_precomp = risk_probe(None, page)
                except Exception:
                    risk_precomp = {"level": "NONE"}
                try:
                    if risk_precomp and risk_precomp.get("level") in ("R1","R2","R3"):
                        rl_update_risk(account_id, risk_precomp.get("level"), time.time())
                except Exception:
                    pass
                if risk_precomp.get("level") == "R3":
                    # 任何模式下都停止，避免升溫
                    try:
                        from .antibot.risk import screenshot as take_shot
                        screenshots.append(take_shot(page, "gate_pre_composer_r3"))
                    except Exception:
                        pass
                    trace_path = None
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    browser.close()
                    return {
                        "ok": False,
                        "channel": "threads",
                        "permalink": None,
                        "timestamp": None,
                        "retries": retries,
                        "artifacts": {"screenshots": screenshots, "trace": trace_path},
                        "error": {"code": "CHALLENGE_DETECTED", "message": "risk:R3 (pre-composer)"},
                        "risk_summary": risk_summarize("R3"),
                        "risk_triggers": risk_precomp.get("triggers", []),
                        "timeline": [*timeline, {"step": "gate_pre_composer", "blocked": True, "level": "R3"}],
                    }
                if risk_precomp.get("level") in ("R1", "R2") and str(cfg.get("risk", {}).get("mode", "warn")).lower() == "stop":
                    # 在 stop 模式下阻擋（任何 run-mode）
                    action = risk_handle(risk_precomp.get("level"), account_id, account_id, page)
                    try:
                        if isinstance(action.get("screenshot"), str):
                            screenshots.append(action.get("screenshot"))
                    except Exception:
                        pass
                    trace_path = None
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    browser.close()
                    return {
                        "ok": False,
                        "channel": "threads",
                        "permalink": None,
                        "timestamp": None,
                        "retries": retries,
                        "artifacts": {"screenshots": screenshots, "trace": trace_path},
                        "error": {"code": "RATE_LIMIT" if risk_precomp["level"] == "R1" else "FORBIDDEN", "message": f"risk:{risk_precomp['level']} (pre-composer)"},
                        "risk_summary": risk_summarize(risk_precomp.get("level")),
                        "risk_triggers": risk_precomp.get("triggers", []),
                        "timeline": [*timeline, {"step": "gate_pre_composer", "blocked": True, "level": risk_precomp.get("level")}],
                    }
                # 否則僅紀錄警告
                if risk_precomp.get("level") in ("R1","R2"):
                    try:
                        risk_warnings.append({"stage": "pre_composer", "level": risk_precomp.get("level")})
                    except Exception:
                        pass
                if verbose:
                    print("[post] open composer")
                opened = False
                composer_was_opened = False
                # 先嘗試點擊 compose_button 列表
                for sel in resolver.get_all("compose_button"):
                    try:
                        if not enable_composer:
                            continue
                        with_retry(lambda: hover_then_click(page, sel), retries=retries)
                        # 點擊後等候編輯器出現
                        try:
                            # 等任一 editor 候選可見，縮短單次等待避免長時間累積
                            editor_candidates = resolver.get_all("composer_input")
                            any_editor = ", ".join(editor_candidates) if editor_candidates else resolver.get("composer_input")
                            page.wait_for_selector(any_editor, timeout=sel_to)
                            opened = True
                            composer_was_opened = True
                            break
                        except Exception:
                            # 可能按到首頁連結等非 composer 元素，繼續嘗試下一個 selector
                            continue
                    except Exception:
                        continue
                # 若上述均失敗，退而求其次：直接點擊編輯器輸入框（若存在）
                if not opened:
                    for sel in resolver.get_all("composer_input"):
                        try:
                            with_retry(lambda: hover_then_click(page, sel), retries=retries)
                            opened = True
                            composer_was_opened = True
                            break
                        except Exception:
                            continue
                if not opened:
                    raise RuntimeError("無法開啟 composer：compose_button/composer_input 皆失敗")

                t0 = time.time()
                time.sleep(human_delay(0.4, 0.2))
                tl(timeline, "open_composer", ms=int((time.time()-t0)*1000))

                if verbose:
                    print("[post] fill content")
                filled = False if enable_typing else True
                last_editor_sel = None
                for sel in resolver.get_all("composer_input"):
                    try:
                        if enable_typing:
                            # 逐段輸入（人類化 1/4 速度）
                            paragraphs = split_paragraphs(content)
                            with_retry(lambda: type_paragraphs_human_char(page, sel, paragraphs, per_char_ms=tuple(per_char_rng)), retries=retries)
                            filled = True
                            last_editor_sel = sel
                            break
                        else:
                            # 僅聚焦 editor，不輸入
                            page.locator(sel).click(timeout=sel_to)
                            last_editor_sel = sel
                            break
                    except Exception:
                        continue
                if not filled:
                    raise RuntimeError("無法填入內容：composer_input 皆失敗")

                t0 = time.time()
                time.sleep(human_delay(0.4, 0.2))
                tl(timeline, "type", ms=int((time.time()-t0)*1000))

                # 輸入完成後比對與修正（所有模式皆做；三次失敗則取消）
                text_check = None
                text_fix_attempts = 0
                if enable_typing:
                    try:
                        editor_sel = last_editor_sel or resolver.get("composer_input")
                        # 以 p[class] 作比對，更貼近實際渲染結果
                        actual = extract_editor_paragraphs_text(page, editor_sel, para_css)
                        text_check = compare_text(content, actual)
                        while (not text_check.get("match")) and text_fix_attempts < 3:
                            applied = try_fix_small_diff(page, editor_sel, content, actual)
                            text_fix_attempts += 1
                            timeline.append({"step": "text_fix_try", "n": text_fix_attempts, "applied": bool(applied)})
                            if not applied:
                                break
                            actual = extract_editor_paragraphs_text(page, editor_sel, para_css)
                            text_check = compare_text(content, actual)

                        if not text_check.get("match"):
                            if verbose:
                                print("[post] text mismatch after attempts → cancel")
                            # 點擊取消（所有模式一致處理）
                            _attempt_close_composer(page, verbose=verbose)
                            _safe_shot(page, "cancel_after_text_mismatch", screenshots)
                            trace_path = None
                            try:
                                trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                                ctx.tracing.stop(path=trace_path)
                            except Exception:
                                pass
                            browser.close()
                            return {
                                "ok": False,
                                "channel": "threads",
                                "permalink": None,
                                "timestamp": int(time.time()),
                                "retries": retries,
                                "artifacts": {"screenshots": screenshots, "trace": trace_path},
                                "run_mode": run_mode,
                                "text_check": text_check,
                                "text_fix_attempts": text_fix_attempts,
                                "cancel_reason": "text_mismatch",
                                "composer_closed": not _is_composer_open(page),
                                "error": {"code": "TEXT_MISMATCH", "message": "input text differs after fix attempts"},
                            }
                    except Exception:
                        pass

                if dry_run:
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    browser.close()
                    return {"ok": True, "code": ErrorCodes.OK, "message": "dry-run"}

                if verbose:
                    print("[post] submit")
                # 風險 Gate #2：按下發佈之前
                try:
                    risk_presubmit = risk_probe(None, page)
                except Exception:
                    risk_presubmit = {"level": "NONE"}
                try:
                    if risk_presubmit and risk_presubmit.get("level") in ("R1","R2","R3"):
                        rl_update_risk(account_id, risk_presubmit.get("level"), time.time())
                except Exception:
                    pass
                if risk_presubmit.get("level") == "R3":
                    try:
                        from .antibot.risk import screenshot as take_shot
                        screenshots.append(take_shot(page, "gate_pre_submit_r3"))
                    except Exception:
                        pass
                    trace_path = None
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    browser.close()
                    return {
                        "ok": False,
                        "channel": "threads",
                        "permalink": None,
                        "timestamp": None,
                        "retries": retries,
                        "artifacts": {"screenshots": screenshots, "trace": trace_path},
                        "error": {"code": "CHALLENGE_DETECTED", "message": "risk:R3 (pre-submit)"},
                        "risk_summary": risk_summarize("R3"),
                        "risk_triggers": risk_presubmit.get("triggers", []),
                        "timeline": [*timeline, {"step": "gate_pre_submit", "blocked": True, "level": "R3"}],
                    }
                if risk_presubmit.get("level") in ("R1","R2") and str(cfg.get("risk", {}).get("mode", "warn")).lower() == "stop":
                    action = risk_handle(risk_presubmit.get("level"), account_id, account_id, page)
                    try:
                        if isinstance(action.get("screenshot"), str):
                            screenshots.append(action.get("screenshot"))
                    except Exception:
                        pass
                    trace_path = None
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    browser.close()
                    return {
                        "ok": False,
                        "channel": "threads",
                        "permalink": None,
                        "timestamp": None,
                        "retries": retries,
                        "artifacts": {"screenshots": screenshots, "trace": trace_path},
                        "error": {"code": "RATE_LIMIT" if risk_presubmit["level"] == "R1" else "FORBIDDEN", "message": f"risk:{risk_presubmit['level']} (pre-submit)"},
                        "risk_summary": risk_summarize(risk_presubmit.get("level")),
                        "risk_triggers": risk_presubmit.get("triggers", []),
                        "timeline": [*timeline, {"step": "gate_pre_submit", "blocked": True, "level": risk_presubmit.get("level")}],
                    }
                # rehearsal: 不點發佈，僅截圖
                if run_mode == "rehearsal":
                    _safe_shot(page, "composer_open", screenshots)
                    _safe_shot(page, "typed_ready", screenshots)
                    trace_path = None
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    # Reply quick-exit: 不做關閉 composer 與 post-scroll，立即結束（避免多餘互動）
                    try:
                        if isinstance(runtime_overrides, dict) and runtime_overrides.get("reply_quick_exit"):
                            now_ts = time.time()
                            cd = recommend_cooldown(now_ts, rl.get("counters", {}).get("last_post_ts"), {"min_interval_sec": mi, "hour_cap": hc, "day_cap": dc})
                            cadence_warnings = []
                            if cd and cd.get("suggested_sleep_s", 0) > 0:
                                cadence_warnings.append({"reason": cd.get("reason"), "suggested_sleep_s": cd.get("suggested_sleep_s")})
                            audit_record({
                                "timestamp": int(time.time()),
                                "account_id": account_id,
                                "persona_id": f"{account_id}.json",
                                "operation": "post_new",
                                "result": "simulate",
                                "run_mode": run_mode,
                                "simulated_publish": True,
                                "screenshots": screenshots,
                                "trace": trace_path,
                            })
                            browser.close()
                            return {
                                "ok": True,
                                "channel": "threads",
                                "permalink": None,
                                "timestamp": int(time.time()),
                                "retries": retries,
                                "artifacts": {"screenshots": screenshots, "trace": trace_path},
                                "simulated_publish": True,
                                "run_mode": run_mode,
                                "humanize": {"pre_s": (pre or {}).get("duration_s"), "post_s": None, "steps": (pre or {}).get("steps")},
                                "risk_summary": risk_summary,
                                "cadence_warnings": cadence_warnings,
                                "cooldown_recommendation": (cd or {}).get("suggested_sleep_s", 0),
                                "timeline": timeline,
                                "modules": {"scroll": enable_scroll, "composer": enable_composer, "typing": enable_typing},
                                "composer_closed": None,
                                "text_check": text_check,
                                "error": None,
                            }
                    except Exception:
                        pass
                    # 關閉 composer（rehearsal 必須關閉）
                    # 關閉前自然化停頓 1–3 秒
                    time.sleep(random.uniform(1.0, 3.0))
                    composer_closed, close_method = _close_composer_safely(page, verbose=verbose, timeout_ms=1200)
                    tl(timeline, "close_composer", ok=bool(composer_closed), method=close_method)
                    # Post humanize in rehearsal: only if composer is closed
                    post = None
                    if humanize_on:
                        try:
                            if composer_closed and enable_scroll:
                                t0 = time.time()
                                post = scroll_feed_random(
                                    page,
                                    seconds_rng=cfg["humanize"]["post_feed_seconds"],
                                    step_px_rng=cfg["humanize"]["scroll_step_px"],
                                    pause_ms_rng=cfg["humanize"]["scroll_pause_ms"],
                                    micro_mouse=cfg["humanize"].get("micro_mouse", True),
                                )
                                tl(timeline, "post_scroll", ms=int((time.time()-t0)*1000))
                            else:
                                tl(timeline, "post_scroll_skipped", reason="composer_open")
                        except Exception:
                            post = {"duration_s": 0, "steps": 0}
                    # cadence 建議
                    now_ts = time.time()
                    cd = recommend_cooldown(now_ts, rl.get("counters", {}).get("last_post_ts"), {"min_interval_sec": mi, "hour_cap": hc, "day_cap": dc})
                    cadence_warnings = []
                    if cd and cd.get("suggested_sleep_s", 0) > 0:
                        cadence_warnings.append({"reason": cd.get("reason"), "suggested_sleep_s": cd.get("suggested_sleep_s")})
                    audit_record({
                        "timestamp": int(time.time()),
                        "account_id": account_id,
                        "persona_id": f"{account_id}.json",
                        "operation": "post_new",
                        "result": "simulate",
                        "run_mode": run_mode,
                        "simulated_publish": True,
                        "screenshots": screenshots,
                        "trace": trace_path,
                    })
                    browser.close()
                    return {
                        "ok": True,
                        "channel": "threads",
                        "permalink": None,
                        "timestamp": int(time.time()),
                        "retries": retries,
                        "artifacts": {"screenshots": screenshots, "trace": trace_path},
                        "simulated_publish": True,
                        "run_mode": run_mode,
                        "humanize": {"pre_s": (pre or {}).get("duration_s"), "post_s": (post or {}).get("duration_s"), "steps": (post or pre or {}).get("steps")},
                        "risk_summary": risk_summary,
                        "cadence_warnings": cadence_warnings,
                        "cooldown_recommendation": (cd or {}).get("suggested_sleep_s", 0),
                        "timeline": timeline,
                        "modules": {"scroll": enable_scroll, "composer": enable_composer, "typing": enable_typing},
                        "composer_closed": bool(composer_closed),
                        "text_check": text_check,
                        "error": None,
                    }
                dom_neutered = False
                net_intercepts = []
                if run_mode == "dress":
                    # 兩層防護
                    try:
                        dom_neutered = arm_dom_neuter(page, resolver.get("post_submit_button"))
                    except Exception:
                        dom_neutered = False
                    # 允許用旗標關閉網路攔截以做 A/B（若 disable_net_guard=True 則不攔）
                    if not disable_net_guard:
                        try:
                            arm_network_abort(ctx, net_intercepts)
                        except Exception:
                            pass

                submitted = False
                for sel in resolver.get_all("post_submit_button"):
                    try:
                        with_retry(lambda: hover_then_click(page, sel), retries=retries)
                        submitted = True
                        break
                    except Exception:
                        continue
                if not submitted and run_mode != "dress":
                    raise RuntimeError("無法送出貼文：post_submit_button 皆失敗")

                # 提交後截圖
                    if run_mode == "dress":
                        _safe_shot(page, "after_click_blocked", screenshots)
                    else:
                        _safe_shot(page, "after_submit", screenshots)

                if run_mode == "dress":
                    trace_path = None
                    try:
                        trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                        ctx.tracing.stop(path=trace_path)
                    except Exception:
                        pass
                    # Reply quick-exit: 不做 composer 關閉與 post-scroll，立即結束
                    try:
                        if isinstance(runtime_overrides, dict) and runtime_overrides.get("reply_quick_exit"):
                            now_ts2 = time.time()
                            cd2 = recommend_cooldown(now_ts2, rl.get("counters", {}).get("last_post_ts"), {"min_interval_sec": mi, "hour_cap": hc, "day_cap": dc})
                            cadence_warnings2 = []
                            if cd2 and cd2.get("suggested_sleep_s", 0) > 0:
                                cadence_warnings2.append({"reason": cd2.get("reason"), "suggested_sleep_s": cd2.get("suggested_sleep_s")})
                            audit_record({
                                "timestamp": int(time.time()),
                                "account_id": account_id,
                                "persona_id": f"{account_id}.json",
                                "operation": "post_new",
                                "result": "simulate",
                                "run_mode": run_mode,
                                "simulated_publish": True,
                                "publish_guard": {"dom_neutered": bool(dom_neutered), "net_intercepts": net_intercepts},
                                "screenshots": screenshots,
                                "trace": trace_path,
                            })
                            browser.close()
                            return {
                                "ok": True,
                                "channel": "threads",
                                "permalink": None,
                                "timestamp": int(time.time()),
                                "retries": retries,
                                "artifacts": {"screenshots": screenshots, "trace": trace_path},
                                "simulated_publish": True,
                                "run_mode": run_mode,
                                "humanize": {"pre_s": (pre or {}).get("duration_s"), "post_s": None, "steps": (pre or {}).get("steps")},
                                "risk_summary": risk_summary,
                                "cadence_warnings": cadence_warnings2,
                                "cooldown_recommendation": (cd2 or {}).get("suggested_sleep_s", 0),
                                "timeline": timeline,
                                "modules": {"scroll": enable_scroll, "composer": enable_composer, "typing": enable_typing},
                                "composer_closed": None,
                                "text_check": text_check,
                                "error": None,
                            }
                    except Exception:
                        pass
                    # 關閉 composer（dress 也應關閉）
                    # 關閉前自然化停頓 1–3 秒
                    time.sleep(random.uniform(1.0, 3.0))
                    composer_closed, close_method = _close_composer_safely(page, verbose=verbose, timeout_ms=1200)
                    tl(timeline, "close_composer", ok=bool(composer_closed), method=close_method)
                    # optional post humanize in dress: only if composer closed
                    post = None
                    if humanize_on:
                        try:
                            if composer_closed and enable_scroll:
                                t0 = time.time()
                                post = scroll_feed_random(
                                    page,
                                    seconds_rng=cfg["humanize"]["post_feed_seconds"],
                                    step_px_rng=cfg["humanize"]["scroll_step_px"],
                                    pause_ms_rng=cfg["humanize"]["scroll_pause_ms"],
                                    micro_mouse=cfg["humanize"].get("micro_mouse", True),
                                )
                                tl(timeline, "post_scroll", ms=int((time.time()-t0)*1000))
                            else:
                                tl(timeline, "post_scroll_skipped", reason="composer_open")
                        except Exception:
                            post = {"duration_s": 0, "steps": 0}
                    # cadence 建議
                    now_ts2 = time.time()
                    cd2 = recommend_cooldown(now_ts2, rl.get("counters", {}).get("last_post_ts"), {"min_interval_sec": mi, "hour_cap": hc, "day_cap": dc})
                    cadence_warnings2 = []
                    if cd2 and cd2.get("suggested_sleep_s", 0) > 0:
                        cadence_warnings2.append({"reason": cd2.get("reason"), "suggested_sleep_s": cd2.get("suggested_sleep_s")})
                    audit_record({
                        "timestamp": int(time.time()),
                        "account_id": account_id,
                        "persona_id": f"{account_id}.json",
                        "operation": "post_new",
                        "result": "simulate",
                        "run_mode": run_mode,
                        "simulated_publish": True,
                        "publish_guard": {"dom_neutered": bool(dom_neutered), "net_intercepts": net_intercepts},
                        "screenshots": screenshots,
                        "trace": trace_path,
                    })
                    browser.close()
                    return {
                        "ok": True,
                        "channel": "threads",
                        "permalink": None,
                        "timestamp": int(time.time()),
                        "retries": retries,
                        "artifacts": {"screenshots": screenshots, "trace": trace_path},
                        "simulated_publish": True,
                        "run_mode": run_mode,
                        "humanize": {"pre_s": (pre or {}).get("duration_s"), "post_s": (post or {}).get("duration_s"), "steps": (post or pre or {}).get("steps")},
                        "risk_summary": risk_summary,
                        "cadence_warnings": cadence_warnings2,
                        "cooldown_recommendation": (cd2 or {}).get("suggested_sleep_s", 0),
                        "timeline": timeline,
                        "modules": {"scroll": enable_scroll, "composer": enable_composer, "typing": enable_typing},
                        "composer_closed": bool(composer_closed),
                        "text_check": text_check,
                        "error": None,
                    }
            except KeyError as e:
                trace_path = None
                try:
                    trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                    ctx.tracing.stop(path=trace_path)
                except Exception:
                    pass
                audit_record({
                    "timestamp": int(time.time()),
                    "account_id": account_id,
                    "persona_id": f"{account_id}.json",
                    "operation": "post_new",
                    "result": "error",
                    "error": {"code": "SELECTOR_NOT_FOUND", "message": str(e)},
                    "screenshots": screenshots,
                    "trace": trace_path,
                })
                return {
                    "ok": False,
                    "channel": "threads",
                    "permalink": None,
                    "timestamp": None,
                    "retries": retries,
                    "artifacts": {"screenshots": screenshots, "trace": trace_path},
                    "error": {"code": "SELECTOR_NOT_FOUND", "message": str(e)},
                }
            except Exception as e:
                trace_path = None
                try:
                    trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                    ctx.tracing.stop(path=trace_path)
                except Exception:
                    pass
                audit_record({
                    "timestamp": int(time.time()),
                    "account_id": account_id,
                    "persona_id": f"{account_id}.json",
                    "operation": "post_new",
                    "result": "error",
                    "error": {"code": "UNEXPECTED", "message": str(e)},
                    "screenshots": screenshots,
                    "trace": trace_path,
                })
                return {
                    "ok": False,
                    "channel": "threads",
                    "permalink": None,
                    "timestamp": None,
                    "retries": retries,
                    "artifacts": {"screenshots": screenshots, "trace": trace_path},
                    "error": {"code": "UNEXPECTED", "message": str(e)},
                }

            # 送出後風險探測
            risk2 = risk_probe(None, page)
            if risk2.get("level") in ("R1", "R2", "R3"):
                try:
                    rl_update_risk(account_id, risk2.get("level"), time.time())
                except Exception:
                    pass
                action = risk_handle(risk2.get("level"), account_id, account_id, page)
                trace_path = None
                try:
                    trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                    ctx.tracing.stop(path=trace_path)
                except Exception:
                    pass
                risk_summary2 = risk_summarize(risk2.get("level")) if risk2 else {"level": "R0", "suggested_cooldown_s": 0, "hints": []}
                audit_record({
                    "timestamp": int(time.time()),
                    "account_id": account_id,
                    "persona_id": f"{account_id}.json",
                    "operation": "post_new",
                    "result": "risk",
                    "error": {"code": "RATE_LIMIT" if risk2["level"] == "R1" else ("FORBIDDEN" if risk2["level"] == "R2" else "CHALLENGE_DETECTED"), "message": f"risk:{risk2['level']}"},
                    "screenshots": [*screenshots, action.get("screenshot")] if isinstance(action.get("screenshot"), str) else screenshots,
                    "trace": trace_path,
                })
                browser.close()
                return {
                    "ok": False,
                    "channel": "threads",
                    "permalink": None,
                    "timestamp": None,
                    "retries": retries,
                    "artifacts": {"screenshots": [*screenshots, action.get("screenshot")] if isinstance(action.get("screenshot"), str) else screenshots, "trace": trace_path},
                    "error": {"code": "RATE_LIMIT" if risk2["level"] == "R1" else ("FORBIDDEN" if risk2["level"] == "R2" else "CHALLENGE_DETECTED"), "message": f"risk:{risk2['level']}"},
                    "risk_summary": risk_summary2,
                    "risk_triggers": risk2.get("triggers", []),
                    "timeline": timeline,
                }

            ok = confirm_posted(page, resolver, timeout_ms=12000) if run_mode == "live" else True
            # optional post humanize for live/success paths: only if composer was opened and is now closed
            post = None
            # Reply quick-exit: 在 reply 模式下（旗標存在）即使 live 也直接略過 post humanize
            if humanize_on and run_mode in ("dress", "live", "rehearsal") and enable_scroll and 'composer_was_opened' in locals() and composer_was_opened and not (isinstance(runtime_overrides, dict) and runtime_overrides.get("reply_quick_exit")):
                try:
                    closed = not _is_composer_open(page)
                    if not closed and run_mode != "live":
                        if verbose:
                            print("[post] composer open → attempt close before post-scroll (final)")
                        t0c = time.time()
                        closed = _attempt_close_composer(page, verbose=verbose)
                        tl(timeline, "close_composer", ms=int((time.time()-t0c)*1000), ok=bool(closed))
                    if closed:
                        t0 = time.time()
                        post = scroll_feed_random(
                            page,
                            seconds_rng=cfg["humanize"]["post_feed_seconds"],
                            step_px_rng=cfg["humanize"]["scroll_step_px"],
                            pause_ms_rng=cfg["humanize"]["scroll_pause_ms"],
                            micro_mouse=cfg["humanize"].get("micro_mouse", True),
                        )
                        tl(timeline, "post_scroll", ms=int((time.time()-t0)*1000))
                    else:
                        tl(timeline, "post_scroll_skipped", reason="composer_open")
                except Exception:
                    post = {"duration_s": 0, "steps": 0}

            # 審計紀錄
            audit_record({
                "timestamp": int(time.time()),
                "account_id": account_id,
                "persona_id": f"{account_id}.json",
                "operation": "post_new",
                "result": "ok" if ok else "timeout",
                "error": None if ok else {"code": "TIMEOUT", "message": "confirm timeout"},
                "screenshots": screenshots,
                "rate": base_audit.get("rate"),
            })
            trace_path = None
            try:
                trace_path = os.path.join(RUNS_DIR, f"trace_{int(time.time())}.zip")
                ctx.tracing.stop(path=trace_path)
            except Exception:
                pass
            browser.close()
            if ok:
                # 更新計數器
                if run_mode == "live":
                    rl_update(account_id, time.time())
                # cadence 建議
                now_ts3 = time.time()
                cd3 = recommend_cooldown(now_ts3, rl.get("counters", {}).get("last_post_ts"), {"min_interval_sec": mi, "hour_cap": hc, "day_cap": dc})
                cadence_warnings3 = []
                if cd3 and cd3.get("suggested_sleep_s", 0) > 0:
                    cadence_warnings3.append({"reason": cd3.get("reason"), "suggested_sleep_s": cd3.get("suggested_sleep_s")})
                risk_summary2 = risk_summarize(risk2.get("level")) if isinstance(risk2, dict) else risk_summary
                return {
                    "ok": True,
                    "channel": "threads",
                    "permalink": None,
                    "timestamp": int(time.time()),
                    "retries": retries,
                    "artifacts": {"screenshots": screenshots, "trace": trace_path},
                    "simulated_publish": False if run_mode == "live" else True,
                    "run_mode": run_mode,
                    "humanize": {"pre_s": (pre or {}).get("duration_s"), "post_s": (post or {}).get("duration_s"), "steps": (post or pre or {}).get("steps")},
                    "risk_summary": risk_summary2,
                    "risk_triggers": (risk2.get("triggers", []) if isinstance(risk2, dict) else risk.get("triggers", [])),
                    "cadence_warnings": cadence_warnings3,
                    "cooldown_recommendation": (cd3 or {}).get("suggested_sleep_s", 0),
                    "timeline": timeline,
                    "modules": {"scroll": enable_scroll, "composer": enable_composer, "typing": enable_typing},
                    "composer_closed": not _is_composer_open(page),
                    "text_check": text_check,
                    "error": None,
                }
            return {
                "ok": False,
                "channel": "threads",
                "permalink": None,
                "timestamp": None,
                "retries": retries,
                "artifacts": {"screenshots": screenshots, "trace": trace_path},
                "error": {"code": "TIMEOUT", "message": "confirm timeout"},
            }
    except Exception as e:
        return {
            "ok": False,
            "channel": "threads",
            "permalink": None,
            "timestamp": None,
            "retries": retries if isinstance(retries, int) else 0,
            "artifacts": {"screenshots": []},
            "error": {"code": "UNEXPECTED", "message": str(e)},
        }


def run_reply_flow(
    permalink: str,
    content: str,
    headless: bool = True,
    selectors_path: Optional[str] = None,
    timeout_ms: int = 2500,
    dry_run: bool = False,
    retries: int = 1,
    verbose: bool = False,
    account_id: str = "default",
    sel_reply: Optional[str] = None,
    sel_editor: Optional[str] = None,
    sel_submit: Optional[str] = None,
    rate_mode: str = "observe",
    run_mode: str = "rehearsal",
    ignore_risk_for_check: bool = False,
    min_interval_sec: Optional[int] = None,
    hour_cap: Optional[int] = None,
    day_cap: Optional[int] = None,
    skip_init_patches: bool = False,
    disable_net_guard: bool = False,
    disable_domain_pin: bool = False,
    disable_header_sanitize: bool = False,
    humanize_session: Optional[str] = None,
    runtime_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Thin wrapper: reuse Mode 1 flow (post_new) by overriding selectors and navigating to the permalink.
    - Compose button → reply icon
    - Composer input → reply editor
    - Submit button → prepend reply publish candidates (+ optional CLI submit) before base
    - Profile URL → target permalink (post_new will navigate there)
    """
    from .config.loader import load_runtime_cfg
    # 注入一個旗標，讓主流程在 thread 頁面不要做 pre-scroll，直接開啟 composer
    injected_overrides = dict(runtime_overrides or {})
    injected_overrides.setdefault("skip_thread_pre_scroll", True)
    injected_overrides.setdefault("reply_quick_exit", True)
    cfg = load_runtime_cfg(overrides=injected_overrides)

    # Build overrides
    # 1) create button = reply icon
    sel_create = sel_reply or (((cfg.get("reply", {}) or {}).get("selectors", {}) or {}).get("reply_icon_svg"))
    # 2) editor = reply editor_input
    sel_editor_eff = sel_editor or (((cfg.get("reply", {}) or {}).get("selectors", {}) or {}).get("editor_input"))
    # 3) submit = [CLI sel_submit?] + reply.publish_candidates + base post_submit_button
    base_selectors = load_selectors(selectors_path or DEFAULT_SELECTORS)
    base_submit = base_selectors.get("post_submit_button", "")
    reply_submit_list = []
    if sel_submit and str(sel_submit).strip():
        reply_submit_list.append(str(sel_submit).strip())
    try:
        reply_submit_list.extend([s for s in ((cfg.get("reply", {}) or {}).get("selectors", {}) or {}).get("publish_candidates", []) if isinstance(s, str) and s.strip()])
    except Exception:
        pass
    merged_submit = ", ".join([*(reply_submit_list or []), base_submit]) if base_submit else ", ".join(reply_submit_list or [])

    # Delegate to Mode 1 flow
    return post_new(
        content=content,
        headless=headless,
        selectors_path=selectors_path,
        timeout_ms=timeout_ms,
        dry_run=dry_run,
        retries=retries,
        verbose=verbose,
        account_id=account_id,
        sel_create=sel_create,
        sel_editor=sel_editor_eff,
        sel_publish=merged_submit if merged_submit else None,
        rate_mode=rate_mode,
        run_mode=run_mode,
        ignore_risk_for_check=ignore_risk_for_check,
        min_interval_sec=min_interval_sec,
        hour_cap=hour_cap,
        day_cap=day_cap,
        profile_url=permalink,
        profile_handle=None,
        skip_init_patches=skip_init_patches,
        disable_net_guard=disable_net_guard,
        disable_domain_pin=disable_domain_pin,
        disable_header_sanitize=disable_header_sanitize,
        humanize_session=humanize_session,
        runtime_overrides=injected_overrides,
    )
