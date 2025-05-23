from agentos.regional.manager import RegionalAgentMonitor
from agentos.agent.proxy import AgentProxy, AgentInfo
from agentos.utils.ready import is_url_ready
from agentos.tasks.elem import TaskEvent, TaskEventType, TaskNode
from agentos.tasks.executor import SimpleTreeTaskExecutor
from typing import List, Any
from multiprocessing import Process
import multiprocessing as mp
import threading as th
import aiohttp
import asyncio
import pytest

generation_prompt_template = \
'''{instructions}

Make a plan then generate the output. If given a Draft Plan, then refine the Draft Plan and then generate the output. Your output should be of the following format:

Plan:
Your plan here.

Output:
Your {output_name} here'''

monitor_host = "127.0.0.1"
monitor_port = 10001
monitor_url = f'http://{monitor_host}:{monitor_port}'

proxy_host = "127.0.0.1"
proxy_port_base = 11000

def run_monitor():
    try:
        monitor = RegionalAgentMonitor()
        monitor.run(monitor_host, monitor_port)
    except Exception as e:
        print(f'Exception: {e}')
        raise e

def run_proxy(id: str, host: str, port: int):
    try:
        proxy = AgentProxy(id, monitor_url, 10)
        proxy.run(host, port)
    except Exception as e:
        print(f'Exception: {e}')
        raise e

@pytest.mark.asyncio
async def test_executor():
    try:
        monitor_process = mp.Process(target=run_monitor)
        monitor_process.start()

        assert await is_url_ready(monitor_url)

        proxy_processes: List[Process] = []
        proxy_ids = []
        proxy_urls = []
        proxies = dict()
        proxies_num = 5
        for i in range(proxies_num):
            proxy_id = f'agent-{i}'
            proxy_port = proxy_port_base+i
            proxy_url = f'http://{proxy_host}:{proxy_port_base+i}'
            proxy_process = mp.Process(target=run_proxy, args=(proxy_id, proxy_host, proxy_port))
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
            assert await is_url_ready(proxy_url)

        task_name = 'MULTITHREADED BLOCKED MATRIX MULTIPLICATION IN C++'
        task_instructions = f'Given a code generation task, write most efficient and fully correct code. The task is: {task_name}'
        task_description = generation_prompt_template.format(
            instructions = task_instructions,
            output_name = "code"
        )
        task_evaluation = 'Given an instruction and several choices, decide which choice is most promising. Analyze each choice in detail, then conclude in the LAST LINE WITH THIS EXACT PATTERN "The best choice is {s}", where s is the integer id of the choice.'
        task_node = TaskNode(
            description=task_description,
            evaluation=task_evaluation,
            n_rounds=2,
            n_samples=5,
            n_voters=3,
        )

        def get_agents():
            return proxies

        task_executor = SimpleTreeTaskExecutor(1, task_node, get_agents)
        await task_executor.start()
        print(f'Result: {task_executor.result}')
        assert not task_executor.failed
        assert task_executor.result is not None

    finally:
        monitor_process.terminate()
        for proxy_process in proxy_processes:
            proxy_process.terminate()
    
        monitor_process.join()
        for proxy_process in proxy_processes:
            proxy_process.join()