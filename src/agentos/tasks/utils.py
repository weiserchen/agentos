from typing import Dict, List, Any
import json
import asyncio
import aiohttp

async def fetch(url: str) -> Dict[str, Any]:
    result = dict()
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            result['status'] = response.status
            if response.status > 200:
                return
            
            body = await response.text()
            result['body'] = json.loads(body)
            return result

async def fetch_all(urls: List[str]) -> List[Dict[str, Any]]:
    tasks = [fetch(url) for url in urls]  
    results = await asyncio.gather(*tasks)         
    return results