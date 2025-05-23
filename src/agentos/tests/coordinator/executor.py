import asyncio
import multiprocessing as mp
from multiprocessing import Process
from typing import List

import pytest

from agentos.agent.proxy import AgentInfo, AgentProxy
from agentos.regional.manager import RegionalAgentMonitor
from agentos.tasks.elem import TaskNode
from agentos.tasks.executor import SimpleTreeTaskExecutor
from agentos.tasks.generate_task import get_task_description
from agentos.utils.logger import AsyncLogger
from agentos.utils.ready import is_url_ready

monitor_host = "127.0.0.1"
monitor_port = 10001
monitor_url = f"http://{monitor_host}:{monitor_port}"

proxy_host = "127.0.0.1"
proxy_port_base = 11000
heartbeat_interval = 10


def run_monitor():
    try:
        monitor = RegionalAgentMonitor()
        monitor.run(monitor_host, monitor_port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


def run_proxy(id: str, host: str, port: int):
    try:
        proxy = AgentProxy(id, monitor_url, heartbeat_interval)
        proxy.run(host, port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


@pytest.mark.asyncio
async def test_executor():
    try:
        pytest_logger = AsyncLogger("pytest")
        await pytest_logger.start()

        monitor_process = mp.Process(target=run_monitor)
        monitor_process.start()

        assert await is_url_ready(pytest_logger, monitor_url)

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
                target=run_proxy, args=(proxy_id, proxy_host, proxy_port)
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
            assert await is_url_ready(pytest_logger, proxy_url)

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

        executor_logger = AsyncLogger("executor")
        await executor_logger.start()

        task_executor = SimpleTreeTaskExecutor(executor_logger, 1, task_node, proxies)
        await task_executor.start()
        await executor_logger.debug(f"Result: \n{task_executor.result}")

        assert not task_executor.failed
        assert task_executor.result is not None

    finally:
        await asyncio.gather(pytest_logger.stop(), executor_logger.stop())

        monitor_process.terminate()
        for proxy_process in proxy_processes:
            proxy_process.terminate()

        monitor_process.join()
        for proxy_process in proxy_processes:
            proxy_process.join()
