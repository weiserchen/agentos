import asyncio

import aiohttp

from agentos.utils.logger import AsyncLogger


async def is_url_ready(logger: AsyncLogger, url: str) -> bool:
    MAX_RETRY = 10
    async with aiohttp.ClientSession() as session:
        for i in range(MAX_RETRY):
            try:
                async with session.get(url + "/ready") as response:
                    assert response.status < 300
                    return True

            except Exception as e:
                if i == MAX_RETRY - 1:
                    await logger.error(e)
                    return False
                else:
                    await logger.warning(e)
                    await asyncio.sleep(0.5)
    return False
