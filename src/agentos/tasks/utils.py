from typing import Any, Dict

import aiohttp


async def http_get(url: str) -> Dict[str, Any]:
    result = dict()
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            result["status"] = response.status
            if response.status > 200:
                result["success"] = False
                return

            result["body"] = await response.json()
            result["success"] = True
            return result


async def http_post(url: str, body: Dict) -> Any:
    result = dict()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body) as response:
                result["status"] = response.status
                if response.status > 300:
                    result["success"] = False
                    return

                result["body"] = await response.json()
                result["success"] = True
                return result
    except Exception:
        result["success"] = False
        return result


async def http_post_with_exception(url: str, data: Dict, name: str):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            assert response.status < 300, (
                f"{name} update - error status code: {response.status} - {data}"
            )
            body = await response.json()
            assert body["success"], (
                f"{name} update - request not successful - {body['err']}"
            )


async def http_put_with_exception(url: str, data: Dict, name: str):
    async with aiohttp.ClientSession() as session:
        async with session.put(url, json=data) as response:
            assert response.status < 300, (
                f"{name} update - error status code: {response.status} - {data}"
            )
            body = await response.json()
            assert body["success"], (
                f"{name} update - request not successful - {body['err']}"
            )
