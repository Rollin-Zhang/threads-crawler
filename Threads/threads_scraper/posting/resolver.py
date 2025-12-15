from typing import Dict, List


class SelectorResolver:
    """Resolve CSS selectors by key with basic validation.
    """

    def __init__(self, selectors: Dict[str, str]):
        self._selectors = selectors

    def get_all(self, key: str) -> List[str]:
        if key not in self._selectors:
            raise KeyError(f"找不到 selector: {key}")
        raw = str(self._selectors[key])
        parts = [p.strip() for p in raw.split(',')]
        parts = [p for p in parts if p]
        if not parts:
            raise ValueError(f"selector 值為空: {key}")
        # 僅允許 CSS，不接受 XPath 片段
        for v in parts:
            if v.startswith('//') or v.startswith('.//'):
                raise ValueError(f"僅允許 CSS 選擇器，不支援 XPath: {key}")
        return parts

    def get(self, key: str) -> str:
        return self.get_all(key)[0]
