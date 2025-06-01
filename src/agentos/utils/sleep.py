import asyncio
import random


async def random_sleep(sleep_interval):
    r = random.random()
    random_interval = sleep_interval * (r * 0.5 + 0.75)
    await asyncio.sleep(random_interval)
