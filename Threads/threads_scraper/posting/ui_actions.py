import time
import random
from typing import Any, Callable, Optional


def _jitter(base: float = 0.25, spread: float = 0.18) -> float:
    return max(0.0, random.uniform(base - spread, base + spread))


def click(page: Any, selector: str, timeout: float = 5000) -> None:
    page.wait_for_selector(selector, timeout=timeout)
    time.sleep(_jitter())
    page.click(selector)


def fill_rich_text(page: Any, selector: str, text: str, timeout: float = 5000) -> None:
    page.wait_for_selector(selector, timeout=timeout)
    time.sleep(_jitter())
    el = page.query_selector(selector)
    if el is None:
        raise RuntimeError(f"找不到元素: {selector}")
    # 嘗試清空（contenteditable）
    el.evaluate("(e) => { e.innerHTML = ''; e.textContent = ''; }")
    el.type(text, delay=int(30 + random.random() * 70))


def wait_text(page: Any, selector: str, timeout: float = 5000) -> bool:
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        return True
    except Exception:
        return False


def with_retry(fn: Callable[[], Any], retries: int = 2, base_delay: float = 0.35) -> Any:
    last_err: Optional[Exception] = None
    for _ in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            time.sleep(base_delay + _jitter(0.3, 0.25))
    if last_err:
        raise last_err
    raise RuntimeError("未知錯誤：with_retry 無回傳且無錯誤")
