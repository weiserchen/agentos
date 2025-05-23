import asyncio
import multiprocessing as mp
from multiprocessing import Process
from typing import List

import aiohttp
import pytest

from agentos.agent.proxy import AgentInfo, AgentProxy
from agentos.regional.manager import RegionalAgentMonitor, RegionalGateway
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
heartbeat_interval = 10
sem_cap = 3


def run_gateway():
    try:
        gateway = RegionalGateway(monitor_url)
        gateway.run(gateway_host, gateway_port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


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
            sem_cap=sem_cap,
        )
        proxy.run(domain, host, port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


@pytest.mark.asyncio
async def test_gateway():
    try:
        logger = AsyncLogger("pytest")
        await logger.start()

        monitor_process = mp.Process(target=run_monitor)
        monitor_process.start()

        assert await is_url_ready(logger, monitor_url)

        proxy_processes: List[Process] = []
        proxy_ids = []
        proxy_urls = []
        proxies = dict()
        proxies_num = 5
        for i in range(proxies_num):
            proxy_id = f"agent-{i}"
            proxy_port = proxy_port_base + i
            proxy_url = f"http://{proxy_host}:{proxy_port_base + i}"
            proxy_process = mp.Process(
                target=run_proxy, args=(proxy_id, proxy_domain, proxy_host, proxy_port)
            )
            proxies[proxy_id] = AgentInfo(
                id=proxy_id,
                addr=proxy_url,
                workload=0,
            )
            proxy_ids.append(proxy_id)
            proxy_urls.append(proxy_url)
            proxy_processes.append(proxy_process)
            proxy_process.start()

        for proxy_url in proxy_urls:
            assert await is_url_ready(logger, proxy_url)

        gateway_process = mp.Process(target=run_gateway)
        gateway_process.start()

        assert await is_url_ready(logger, gateway_url)

        data = {
            "task_name": "code_generation",
            "task_description": "MULTITHREADED BLOCKED MATRIX MULTIPLICATION IN C++",
        }

        task_id = None
        async with aiohttp.ClientSession() as session:
            async with session.post(gateway_url + "/query", json=data) as response:
                assert response.status < 300
                body = await response.json()
                assert body["success"]
                task_id = body["task_id"]

        sleep_interval = 10
        while True:
            async with aiohttp.ClientSession() as session:
                data = {
                    "task_id": task_id,
                }
                async with session.get(
                    gateway_url + "/task/status", params=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    status = body["status"]
                    if status == "not exist":
                        error_str = f"task {task_id} not exist"
                        await logger.error(f"[Task {task_id}] {error_str}")
                        raise Exception(f"task {task_id} not exist")
                    elif status == "ok":
                        assert body["success"]
                        result = body["result"]
                        assert result != ""
                        await logger.debug(f"[Task {task_id}] result: \n{result}")
                        break
                    else:
                        await logger.warning(f"[Task {task_id}] waiting for result...")
                        await asyncio.sleep(sleep_interval)

    finally:
        await logger.stop()

        monitor_process.terminate()
        gateway_process.terminate()
        for proxy_process in proxy_processes:
            proxy_process.terminate()

        monitor_process.join()
        gateway_process.join()
        for proxy_process in proxy_processes:
            proxy_process.join()
