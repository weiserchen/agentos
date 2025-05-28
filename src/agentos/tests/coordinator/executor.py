import multiprocessing as mp
from multiprocessing import Process
from typing import List

import pytest

from agentos.agent.proxy import AgentInfo, AgentProxy
from agentos.regional.manager import RegionalAgentMonitor
from agentos.tasks.coordinator import SingleNodeCoordinator
from agentos.tasks.elem import TaskNode
from agentos.tasks.generate_task import get_task_description
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
async def test_executor():
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

        task_name = "code_generation"
        query = "MULTITHREADED BLOCKED MATRIX MULTIPLICATION IN C++"
        task_description = get_task_description(task_name, query)
        task_evaluation = 'Given an instruction and several choices, decide which choice is most promising. Analyze each choice in detail, then conclude in the LAST LINE WITH THIS EXACT PATTERN "The best choice is {s}", where s is the integer id of the choice.'
        task_node = TaskNode(
            description=task_description,
            evaluation=task_evaluation,
            n_rounds=2,
            n_samples=5,
            n_voters=3,
        )

        async def get_agents():
            return proxies

        task_coordinator = SingleNodeCoordinator(1, task_node, get_agents)
        await task_coordinator.start()
        await logger.debug(f"Result: \n{task_coordinator.result}")

        assert task_coordinator.success
        assert task_coordinator.result is not None

    finally:
        await logger.stop()

        monitor_process.terminate()
        for proxy_process in proxy_processes:
            proxy_process.terminate()

        monitor_process.join()
        for proxy_process in proxy_processes:
            proxy_process.join()
