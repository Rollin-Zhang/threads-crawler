import os
from typing import Optional


def storage_state_path() -> str:
    """Return absolute path for storage_state.json within threads_scraper folder."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, "..", "storage_state.json"))


def ensure_storage_state() -> Optional[str]:
    """If storage_state.json exists, return its absolute path; else None.

    Note: Creating or refreshing state is handled by login flows; this util is a lightweight checker.
    """
    p = storage_state_path()
    return p if os.path.exists(p) else None
