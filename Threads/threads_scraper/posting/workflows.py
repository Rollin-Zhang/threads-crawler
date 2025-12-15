import os
from typing import Optional


def read_content(file_path: Optional[str]) -> str:
    # 優先讀取外部文字檔；否則讀 default
    if file_path and os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    default_path = os.path.join(os.path.dirname(__file__), "config", "new_post_content.txt")
    with open(default_path, "r", encoding="utf-8") as f:
        return f.read().strip()
