import asyncio
import multiprocessing as mp

import aiohttp
import pytest

from agentos.agent.proxy import AgentProxy
from agentos.regional.manager import RegionalAgentMonitor
from agentos.utils.logger import AsyncLogger
from agentos.utils.ready import is_url_ready

gateway_host = "127.0.0.1"
gateway_port = 10000
gateway_url = f"http://{gateway_host}:{gateway_port}"

monitor_host = "127.0.0.1"
monitor_port = 10001
monitor_url = f"http://{monitor_host}:{monitor_port}"


proxy_domain = "127.0.0.1"
proxy_host = "127.0.0.1"
proxy_port = 11000
proxy_id = "agent-0"
proxy_url = f"http://{proxy_host}:{proxy_port}"
heartbeat_interval = 5


def run_monitor():
    try:
        monitor = RegionalAgentMonitor()
        monitor.run(monitor_host, monitor_port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


def run_proxy(id: str, domain: str, host: str, port: int):
    try:
        proxy = AgentProxy(
            id,
            gateway_url,
            monitor_url,
            update_interval=heartbeat_interval,
        )
        proxy.run(domain, host, port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


@pytest.mark.asyncio
async def test_agent_proxy():
    try:
        logger = AsyncLogger("pytest")
        await logger.start()

        monitor_process = mp.Process(target=run_monitor)
        monitor_process.start()

        assert await is_url_ready(logger, monitor_url)

        await logger.info("monitor started.")

        proxy_process = mp.Process(
            target=run_proxy, args=(proxy_id, proxy_domain, proxy_host, proxy_port)
        )
        proxy_process.start()

        assert await is_url_ready(logger, proxy_url)

        await logger.info("proxies started.")

        MAX_RETRY = 3
        view_ok = False
        async with aiohttp.ClientSession() as session:
            for i in range(MAX_RETRY):
                async with session.get(proxy_url + "/membership/view") as response:
                    assert response.status < 300
                    body = await response.json()
                    agents = body["agents"]
                    await logger.info(f"agents: {agents}")
                    if len(agents) == 1:
                        view_ok = True
                        break

                    await asyncio.sleep(0.5)

        assert view_ok

        async with aiohttp.ClientSession() as session:
            data = {
                "task_id": 1,
                "task_round": 0,
                "task_action": "generation",
                "task_description": "A travel plan to Irvine",
                "task_stop": None,
            }
            async with session.post(proxy_url + "/agent/call", json=data) as response:
                assert response.status < 300
                body = await response.json()
                result = body["result"]
                await logger.info(f"Result: \n{result}")

    finally:
        await logger.stop()

        monitor_process.terminate()
        monitor_process.join()

        proxy_process.terminate()
        proxy_process.join()
