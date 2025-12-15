import random
import asyncio


def human_delay(base: float = 0.35, jitter: float = 0.22) -> float:
    return max(0.0, random.uniform(base - jitter, base + jitter))


async def sleep_human(base: float = 0.35, jitter: float = 0.22) -> None:
    await asyncio.sleep(human_delay(base, jitter))
