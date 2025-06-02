from typing import Any, Dict
import aiohttp
import asyncio
import atexit

# Singleton (shared) ClientSession
_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()


async def _get_session() -> aiohttp.ClientSession:
    """
    Return a shared aiohttp.ClientSession, creating it lazily on first use.
    """
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            timeout = aiohttp.ClientTimeout( 
                sock_connect=30,                      # TCP / TLS handshake
                sock_read=300,                        # server->client stream
                total=None,                           # no overall cap
            )
            connector = aiohttp.TCPConnector(limit=0)
            _session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            )
    return _session


async def _close_session() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()

atexit.register(lambda: asyncio.run(_close_session()))

async def http_post(url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    JSON POST helper that reuses one ClientSession for the whole process.
    """
    session = await _get_session()
    result: Dict[str, Any] = {}
    try:
        async with session.post(url, json=body) as resp:
            result["status"] = resp.status
            result["body"]   = await resp.json()
            result["success"] = resp.status < 300
    except Exception as e:
        result["success"] = False
        result["error"]   = repr(e)
    return result

async def http_get(url: str, params: Dict | None = None) -> Dict[str, Any]:
    """
    JSON GET helper that reuses one ClientSession for the whole process.
    """
    session = await _get_session()
    result: Dict[str, Any] = {}
    try:
        async with session.get(url, params=params) as resp:
            result["status"]  = resp.status
            result["body"]    = await resp.json()
            result["success"] = resp.status < 300
    except Exception as e:
        result["success"] = False
        result["error"]   = repr(e)
    return result