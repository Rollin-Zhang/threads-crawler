import os
import json
from typing import Optional, Tuple

from .state_manager import storage_state_path as _storage_state_path
from .cookies_to_storage import convert_cookies_to_storage_state


def paths() -> Tuple[str, str]:
    base = os.path.dirname(os.path.abspath(__file__))
    cookies = os.path.normpath(os.path.join(base, "..", "cookies.json"))
    storage = os.path.normpath(os.path.join(base, "..", "storage_state.json"))
    return cookies, storage


def ensure_storage_state_from_cookies(logger: Optional[object] = None) -> str:
    """If storage_state.json is missing but cookies.json exists, convert it.
    Return storage_state path (may or may not exist after conversion attempt).
    """
    cookies_path, storage_path = paths()
    if not os.path.exists(storage_path) and os.path.exists(cookies_path):
        try:
            convert_cookies_to_storage_state(cookies_path, storage_path)
            if logger:
                _log(logger, f"[cookies->storage_state] 已轉換：{cookies_path} -> {storage_path}")
        except Exception as e:
            if logger:
                _log(logger, f"[cookies->storage_state] 轉換失敗：{e}")
    return storage_path


def verify_and_persist(page, logger: Optional[object] = None) -> bool:
    """Open page already created; fast-check login state using cookies first,
    then (if needed) lightweight selector checks. Persist cookies and storage_state in all cases.
    """
    try:
        # 限縮 domcontentloaded 等待，避免在首頁卡過久
        try:
            page.wait_for_load_state("domcontentloaded", timeout=2000)
        except Exception:
            pass

        # 先用 cookies 快速判定，通常這一步就足夠
        logged_in = False
        try:
            names = {c.get('name') for c in page.context.cookies()}
            if {'sessionid', 'ds_user_id', 'mid'} & names:
                logged_in = True
        except Exception:
            logged_in = False

        # 若 cookies 無法判定，再做短 timeout 的 selector 探測
        if not logged_in:
            selectors = [
                'button[aria-label*="建立串文"]',
                'textarea[placeholder*="建立串文"]',
                'text=建立串文',
                'a[role="link"][href^="/@"]',
            ]
            for sel in selectors:
                try:
                    page.wait_for_selector(sel, timeout=1200)
                    logged_in = True
                    break
                except Exception:
                    continue

        _persist_context(page, logger)
        if logged_in:
            _log(logger, "[storage_state] 已判定為登入狀態（cookie/selector）。")
        else:
            _log(logger, "[storage_state] 無法判定登入狀態，可能為未登入或 UI 改變。")
        return logged_in
    except Exception as e:
        _log(logger, f"[storage_state] 驗證或保存狀態時發生異常：{e}")
        try:
            _persist_context(page, logger)
        except Exception:
            pass
        return False


def _persist_context(page, logger: Optional[object] = None) -> None:
    base = os.path.dirname(os.path.abspath(__file__))
    cookies_path = os.path.normpath(os.path.join(base, "..", "cookies.json"))
    storage_path = os.path.normpath(os.path.join(base, "..", "storage_state.json"))
    cookies = page.context.cookies()
    with open(cookies_path, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, ensure_ascii=False)
    page.context.storage_state(path=storage_path)
    _log(logger, f"[login] 狀態已保存：cookies->{cookies_path}, storage_state->{storage_path}")


def _log(logger: Optional[object], msg: str):
    if logger is None:
        print(msg)
    else:
        # 支援 scrapy logger 或一般 logger
        if hasattr(logger, 'info'):
            try:
                logger.info(msg)
                return
            except Exception:
                pass
        print(msg)
