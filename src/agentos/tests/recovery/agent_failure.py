import asyncio
import logging
import multiprocessing as mp
import random
from multiprocessing import Process
from typing import List

import pytest

from agentos.agent.proxy import AgentInfo, AgentProxy
from agentos.service.monitor import AgentMonitorServer
from agentos.tasks.coordinator import SingleNodeCoordinator
from agentos.tasks.elem import TaskNode
from agentos.tasks.generate_task import get_task_description
from agentos.utils.logger import AsyncLogger
from agentos.utils.ready import is_url_ready
from agentos.utils.sleep import random_sleep

gateway_host = "127.0.0.1"
gateway_port = 10000
gateway_url = f"http://{gateway_host}:{gateway_port}"

monitor_host = "127.0.0.1"
monitor_port = 10001
monitor_url = f"http://{monitor_host}:{monitor_port}"

dbserver_host = "127.0.0.1"
dbserver_port = 10002
dbserver_url = f"http://{dbserver_host}:{dbserver_port}"

proxy_domain = "127.0.0.1"
proxy_host = "127.0.0.1"
proxy_port_base = 11000
heartbeat_interval = 10
sem_cap = 3


def run_monitor():
    try:
        monitor = AgentMonitorServer(log_level=logging.DEBUG)
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
            dbserver_url,
            update_interval=heartbeat_interval,
            sem_cap=sem_cap,
            log_level=logging.DEBUG,
        )
        proxy.run(domain, host, port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


@pytest.mark.asyncio
async def test_agent_recovery():
    try:
        logger = AsyncLogger("pytest", level=logging.DEBUG)
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
        n_rounds = 2
        n_samples = 5
        n_voters = 3
        task_node = TaskNode(
            description=task_description,
            evaluation=task_evaluation,
            n_rounds=n_rounds,
            n_samples=n_samples,
            n_voters=n_voters,
        )

        async def get_agents():
            return proxies

        task_id = 1
        curr_round = 0
        curr_term = 0
        curr_result = ""
        task_coordinator = SingleNodeCoordinator(
            task_id,
            curr_round,
            curr_term,
            curr_result,
            task_node,
            get_agents,
        )

        async def kill_random_proxies(k: int, sleep_interval: int):
            proxy_idxs = random.sample([i for i in range(len(proxy_ids))], k=k)
            await logger.warning(f"trying to kill proxies: {proxy_idxs}")
            for idx in proxy_idxs:
                await random_sleep(sleep_interval)
                await logger.warning(f"killing proxy {idx}")
                proxy_processes[idx].terminate()
                proxy_processes[idx].join()

        asyncio.create_task(kill_random_proxies(2, 15))

        async for _ in task_coordinator.run():
            assert task_coordinator.round == curr_round
            assert task_coordinator.result != curr_result
            curr_round += 1
            curr_result = task_coordinator.result
            if task_coordinator.round == n_rounds - 1:
                assert task_coordinator.success
                assert task_coordinator.completed
            else:
                assert not task_coordinator.success
                assert not task_coordinator.completed

        await logger.debug(f"Result: \n{task_coordinator.result}")

        assert task_coordinator.completed
        assert task_coordinator.success
        assert task_coordinator.result != ""

    finally:
        await logger.stop()

        monitor_process.terminate()
        for proxy_process in proxy_processes:
            proxy_process.terminate()

        monitor_process.join()
        for proxy_process in proxy_processes:
            proxy_process.join()
