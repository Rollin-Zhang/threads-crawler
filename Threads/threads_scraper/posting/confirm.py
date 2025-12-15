from .resolver import SelectorResolver
from .ui_actions import wait_text


def confirm_posted(page, resolver: SelectorResolver, timeout_ms: int = 12000) -> bool:
    for sel in resolver.get_all("post_success_toast"):
        if wait_text(page, sel, timeout=timeout_ms):
            return True
    return False
