import os
from typing import Dict, Optional

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # graceful fallback


DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "config", "selectors.yaml")


def _parse_kv_fallback(text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 去除行內註解
        if "#" in line:
            line = line.split("#", 1)[0].rstrip()
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        # 去除包裹引號
        if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
            v = v[1:-1]
        if k and v:
            result[k] = v
    return result


def load_selectors(path: Optional[str] = None) -> Dict[str, str]:
    path = path or DEFAULT_CONFIG
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError("selectors.yaml 應為 key/value 組成的 dict")
        parsed = {k: str(v) for k, v in data.items() if isinstance(v, str)}
    else:
        parsed = _parse_kv_fallback(text)
    # 僅允許字串 CSS 選擇器
    return {k: v for k, v in parsed.items() if isinstance(v, str)}
