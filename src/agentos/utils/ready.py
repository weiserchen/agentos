import aiohttp
import asyncio

async def is_url_ready(url: str) -> bool:
    MAX_RETRY = 10
    async with aiohttp.ClientSession() as session:
        for i in range(MAX_RETRY):
            try:
                async with session.get(url+"/ready") as response:
                    assert response.status < 300
                    return True
                
            except Exception as e:
                print(e)
                if i == MAX_RETRY - 1:
                    return False
                else:
                    await asyncio.sleep(0.5)
    return False