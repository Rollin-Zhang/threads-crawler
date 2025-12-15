from __future__ import annotations
import time
import random
import difflib
from typing import Any, Dict, List, Tuple
import re


def split_paragraphs(text: str) -> List[str]:
    # Split by double newlines first; fallback to single newline
    if "\n\n" in text:
        parts = [p for p in (s.strip("\n") for s in text.split("\n\n"))]
    else:
        parts = [p for p in (s.rstrip("\n") for s in text.split("\n"))]
    return parts


def _human_pause(ms_rng: Tuple[int, int] = (150, 480)) -> None:
    time.sleep(random.uniform(ms_rng[0]/1000.0, ms_rng[1]/1000.0))


def type_paragraphs(page: Any, editor_selector: str, paragraphs: List[str],
                    per_para_delay_ms: Tuple[int, int] = (220, 680),
                    inter_para_delay_ms: Tuple[int, int] = (260, 900)) -> None:
    ed = page.locator(editor_selector)
    ed.click()
    for idx, para in enumerate(paragraphs):
        if idx > 0:
            page.keyboard.press("Enter")
            _human_pause(inter_para_delay_ms)
        # Use insert_text for chunk; it preserves newlines less reliably per-char,
        # so we send paragraphs individually to keep cursor at end naturally.
        page.keyboard.insert_text(para)
        _human_pause(per_para_delay_ms)


def type_paragraphs_human_char(
    page: Any,
    editor_selector: str,
    paragraphs: List[str],
    per_char_ms: Tuple[int, int] = (600, 1200),  # 4x slower than 150-300ms
    inter_para_s: Tuple[float, float] = (0.5, 2.0),
) -> None:
    ed = page.locator(editor_selector)
    ed.click()
    for idx, para in enumerate(paragraphs):
        # 在段落間插入換行
        if idx > 0:
            page.keyboard.press("Enter")
            time.sleep(random.uniform(inter_para_s[0], inter_para_s[1]))
        # 逐字輸入
        for ch in para:
            # 使用 type 以便延遲每個鍵
            page.keyboard.type(ch, delay=random.randint(per_char_ms[0], per_char_ms[1]))
            # 偶爾插入極短停頓，避免完全等距
            if random.random() < 0.06:
                time.sleep(random.uniform(0.06, 0.18))
        # 段落尾端輕微停頓
        time.sleep(random.uniform(0.12, 0.4))


def extract_editor_text(page: Any, editor_selector: str) -> str:
    try:
        loc = page.locator(editor_selector)
        # innerText better reflects visual newlines than textContent for contenteditable
        txt = loc.evaluate("el => el.innerText")
        return txt if isinstance(txt, str) else str(txt)
    except Exception:
        return ""


def extract_editor_paragraphs_text(page: Any, editor_selector: str, para_css: str = "p[class]") -> str:
    """Extract text by concatenating innerText of paragraph nodes under editor.
    Defaults to p[class] to target rendered paragraphs; falls back to editor.innerText when empty.
    """
    try:
        loc = page.locator(editor_selector)
        result = loc.evaluate(
            "(el, sel) => {\n"
            "  try {\n"
            "    const nodes = Array.from(el.querySelectorAll(sel));\n"
            "    if (!nodes.length) return { ok: true, paras: [] };\n"
            "    const paras = nodes.map(n => (n.innerText || '').replace(/\\u00a0/g, ' ').replace(/\\s+$/,'') );\n"
            "    return { ok: true, paras };\n"
            "  } catch (e) { return { ok: false, paras: [] }; }\n"
            "}",
            para_css,
        )
        if isinstance(result, dict) and result.get("ok") and result.get("paras"):
            return "\n".join([p if isinstance(p, str) else str(p) for p in result.get("paras", [])])
        # fallback
        return extract_editor_text(page, editor_selector)
    except Exception:
        return extract_editor_text(page, editor_selector)


def _normalize_for_compare(s: str) -> str:
    """Normalize editor and expected text for robust comparison.
    - Normalize newlines to \n
    - Replace NBSP with normal space
    - Trim trailing spaces on each line
    - Collapse multiple blank lines (2+ newlines) to a single newline
    - rstrip overall trailing whitespace
    """
    s = s.replace("\r\n", "\n").replace("\u00a0", " ")
    # Trim end of each line to avoid visual-only spaces
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    # Collapse 2+ newlines to 1 to tolerate different paragraph separations
    s = re.sub(r"\n{2,}", "\n", s)
    return s.rstrip()


def compare_text(expected: str, actual: str) -> Dict[str, Any]:
    exp_norm = _normalize_for_compare(expected)
    act_norm = _normalize_for_compare(actual)
    match = (exp_norm == act_norm)
    diff_excerpt = None
    if not match:
        sm = difflib.SequenceMatcher(a=exp_norm, b=act_norm)
        blocks = sm.get_opcodes()
        # find first non-equal block and extract a small window
        for tag, i1, i2, j1, j2 in blocks:
            if tag != 'equal':
                exp_seg = exp_norm[i1:i2]
                act_seg = act_norm[j1:j2]
                diff_excerpt = f"exp[{i1}:{i2}]='{exp_seg[:60]}' vs act[{j1}:{j2}]='{act_seg[:60]}'"
                break
    return {
        "expected_len": len(exp_norm),
        "actual_len": len(act_norm),
        "match": match,
        "diff_excerpt": diff_excerpt,
    }


def _is_small_diff(expected: str, actual: str) -> bool:
    exp = expected.rstrip()
    act = actual.rstrip()
    if abs(len(exp) - len(act)) > 120:
        return False
    ratio = difflib.SequenceMatcher(a=exp, b=act).ratio()
    return ratio >= 0.95


def try_fix_small_diff(page: Any, editor_selector: str, expected: str, actual: str, max_backspace: int = 150) -> bool:
    """Attempt a minimal fix:
    - If actual is a prefix of expected -> append remainder
    - If expected is a prefix of actual -> backspace the tail up to max_backspace
    Returns True if change applied (may still need re-compare by caller).
    """
    exp = expected.rstrip()
    act = actual.rstrip()
    ed = page.locator(editor_selector)
    ed.click()
    if exp.startswith(act):
        remainder = exp[len(act):]
        if remainder:
            page.keyboard.insert_text(remainder)
            _human_pause((160, 420))
            return True
        return False
    if act.startswith(exp):
        extra = len(act) - len(exp)
        if extra <= max_backspace:
            for _ in range(extra):
                page.keyboard.press("Backspace")
                _human_pause((10, 30))
            return True
        return False
    return False
