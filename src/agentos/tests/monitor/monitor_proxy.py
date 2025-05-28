import asyncio
import multiprocessing as mp
from multiprocessing import Process
from typing import List

import aiohttp
import pytest

from agentos.agent.proxy import AgentProxy
from agentos.regional.monitor import RegionalAgentMonitor
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
proxy_port_base = 11000
heartbeat_interval = 1


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
async def test_agent_monitor_proxy():
    try:
        monitor_process = None
        proxy_processes: List[Process] = []

        logger = AsyncLogger("pytest")
        await logger.start()

        monitor_process = mp.Process(target=run_monitor)
        monitor_process.start()
        assert await is_url_ready(logger, monitor_url)

        await logger.info("monitor started.")

        proxy_ids = []
        proxy_urls = []
        proxies_num = 3
        for i in range(proxies_num):
            proxy_id = f"agent-{i}"
            proxy_port = proxy_port_base + i
            proxy_url = f"http://{proxy_host}:{proxy_port_base + i}"
            proxy_process = mp.Process(
                target=run_proxy, args=(proxy_id, proxy_domain, proxy_host, proxy_port)
            )
            proxy_ids.append(proxy_id)
            proxy_urls.append(proxy_url)
            proxy_processes.append(proxy_process)
            proxy_process.start()

        for proxy_url in proxy_urls:
            assert await is_url_ready(logger, proxy_url)

        await logger.info("proxies started.")

        await asyncio.sleep(3)

        MAX_RETRY = 3
        for i in range(MAX_RETRY):
            try:
                async with aiohttp.ClientSession() as session:
                    # check the monitor has all proxies info
                    async with session.get(monitor_url + "/agent/list") as response:
                        assert response.status < 300
                        body = await response.json()
                        agents = body["agents"]
                        assert len(agents) == proxies_num

                        for i in range(proxies_num):
                            proxy_id = proxy_ids[i]
                            proxy_url = proxy_urls[i]
                            assert proxy_id in agents
                            proxy = agents[proxy_id]
                            assert proxy["addr"] == proxy_url

                    # check all proxies share the same membership view
                    for i in range(proxies_num):
                        proxy_id = proxy_ids[i]
                        proxy_url = proxy_urls[i]
                        async with session.get(
                            proxy_url + "/membership/view"
                        ) as response:
                            assert response.status < 300
                            body = await response.json()
                            agents = body["agents"]
                            assert len(agents) == proxies_num

                            for j in range(proxies_num):
                                agent_id = proxy_ids[j]
                                agent_url = proxy_urls[j]
                                assert agent_id in agents
                                agent = agents[agent_id]
                                assert agent["id"] == agent_id
                                assert agent["addr"] == agent_url

            except Exception as e:
                if i == MAX_RETRY - 1:
                    raise e
                else:
                    await asyncio.sleep(1)

    finally:
        await logger.stop()

        if monitor_process is not None:
            monitor_process.terminate()
        for proxy_process in proxy_processes:
            proxy_process.terminate()

        if monitor_process is not None:
            monitor_process.join()
        for proxy_process in proxy_processes:
            proxy_process.join()
