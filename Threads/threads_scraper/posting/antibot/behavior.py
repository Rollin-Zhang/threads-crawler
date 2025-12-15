import random
import time


def warmup_page(page) -> None:
    # 模擬移動滑鼠
    try:
        x, y = random.randint(50, 400), random.randint(50, 300)
        page.mouse.move(x, y, steps=random.randint(10, 25))
        # 縮短暖身等待
        time.sleep(random.uniform(0.08, 0.20))
        page.mouse.move(x + random.randint(10, 60), y + random.randint(10, 60), steps=random.randint(10, 20))
    except Exception:
        pass

    # 1–2 次滾動（200–350px）
    try:
        for _ in range(random.randint(1, 2)):
            page.mouse.wheel(delta_x=0, delta_y=random.randint(200, 350))
            time.sleep(random.uniform(0.08, 0.20))
    except Exception:
        pass

    time.sleep(random.uniform(0.08, 0.20))


def hover_then_click(page, selector: str) -> None:
    """Hover then click with short explicit timeouts to avoid default 30s stalls.
    If the selector不存在或不可互動，快速失敗讓上層重試下一個候選。
    """
    loc = page.locator(selector)
    # 快速檢查是否有匹配元素，避免 hover/click 等待過久
    try:
        if loc.count() == 0:
            raise RuntimeError(f"no match for: {selector}")
    except Exception:
        # 若 count 失敗，仍嘗試一次，保留向後相容
        pass
    try:
        loc.first.hover(timeout=1200)
        time.sleep(random.uniform(0.08, 0.20))
        loc.first.click(timeout=1200)
    except Exception:
        # fallback: 直接點擊（短 timeout）
        page.click(selector, timeout=1200)


def type_human(page, selector: str, text: str) -> None:
    loc = page.locator(selector)
    loc.click()
    typed = 0
    i = 0
    while i < len(text):
        # 降低 paste 機率以放慢總體輸入速度
        if random.random() < 0.05 and (len(text) - i) > 5:
            chunk_len = random.randint(3, min(12, len(text) - i))
            chunk = text[i:i+chunk_len]
            page.keyboard.insert_text(chunk)
            i += chunk_len
            typed += chunk_len
            time.sleep(random.uniform(0.3, 0.7))
            continue

        # 將打字速度降為原本的約三分之一（增加 per-key 延遲）
        page.keyboard.type(text[i], delay=random.randint(150, 360))
        i += 1
        typed += 1
        if typed % random.randint(15, 25) == 0:
            time.sleep(random.uniform(0.4, 1.0))
