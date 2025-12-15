import random
import time
from typing import Dict, Tuple


def _rand_range(r: Tuple[int, int]) -> int:
    lo, hi = int(r[0]), int(r[1])
    if lo > hi:
        lo, hi = hi, lo
    return random.randint(lo, hi)


def _micro_mouse_move(page, steps: int = 3) -> None:
    try:
        x, y = random.randint(80, 400), random.randint(120, 320)
        page.mouse.move(x, y)
        for _ in range(steps):
            x += random.randint(-20, 20)
            y += random.randint(-12, 12)
            page.mouse.move(x, y, steps=random.randint(5, 12))
            time.sleep(random.uniform(0.03, 0.08))
    except Exception:
        pass


def scroll_feed_random(
    page,
    seconds_rng: Tuple[int, int] = (60, 90),
    step_px_rng: Tuple[int, int] = (80, 200),
    pause_ms_rng: Tuple[int, int] = (200, 480),
    micro_mouse: bool = True,
    max_steps: int | None = None,
    initial_idle_rng: Tuple[int, int] | None = None,
) -> Dict:
    """模擬真人滑動首頁動態牆一段時間。

    - 每 ~0.2–0.5 秒捲動 180–420px（可調）
    - 在過程中隨機 5–10 次插入較長停頓（3-8s）
    - micro_mouse=True 時偶爾微幅移動滑鼠
    """
    start = time.time()
    # 初始靜止數秒，避免一打開頁面就滾動
    if initial_idle_rng is not None:
        idle = _rand_range(initial_idle_rng)
        time.sleep(max(0, idle))
    duration_target = _rand_range(seconds_rng)
    steps = 0
    long_breaks = _rand_range((3, 6))
    long_break_every = max(5, duration_target // max(1, long_breaks))
    try:
        # 初始微幅移動
        if micro_mouse:
            _micro_mouse_move(page, steps=random.randint(2, 4))
        while (time.time() - start) < duration_target:
            # 滾動
            page.mouse.wheel(delta_x=0, delta_y=_rand_range(step_px_rng))
            steps += 1
            if max_steps is not None and steps >= int(max_steps):
                break
            # 偶爾移動滑鼠
            if micro_mouse and (steps % random.randint(6, 12) == 0):
                _micro_mouse_move(page, steps=random.randint(1, 3))
            # 基本短暫停頓
            time.sleep(_rand_range(pause_ms_rng) / 1000.0)
            # 插入較長停頓
            elapsed = time.time() - start
            if int(elapsed) % max(5, long_break_every) == 0 and random.random() < 0.35:
                time.sleep(random.uniform(1.5, 4.0))
            # 偶爾反向微移，避免完全單向
            if random.random() < 0.08:
                page.mouse.wheel(delta_x=0, delta_y=-_rand_range((40, 120)))
                steps += 1
                if max_steps is not None and steps >= int(max_steps):
                    break
    except Exception:
        pass
    return {"duration_s": int(time.time() - start), "steps": steps}
