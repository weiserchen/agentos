import asyncio
import logging
import multiprocessing as mp
import os
from multiprocessing import Process
from typing import List

import pytest

from agentos.agent.proxy import AgentInfo, AgentProxy
from agentos.service.dbserver import AgentDatabaseServer
from agentos.service.gateway import AgentGatewayServer
from agentos.service.monitor import AgentMonitorServer
from agentos.tasks.elem import TaskStatus
from agentos.tasks.utils import http_get, http_post
from agentos.utils.logger import AsyncLogger
from agentos.utils.ready import is_url_ready
from agentos.utils.sleep import random_sleep

gateway_host = "127.0.0.1"
gateway_port = 10000
gateway_url = f"http://{gateway_host}:{gateway_port}"

monitor_host = "127.0.0.1"
monitor_port = 10001
monitor_url = f"http://{monitor_host}:{monitor_port}"

script_dir = os.path.dirname(os.path.abspath(__file__))
db_file = os.path.join(script_dir, "pytest.db")
dbserver_host = "127.0.0.1"
dbserver_port = 10002
dbserver_url = f"http://{dbserver_host}:{dbserver_port}"

proxy_domain = "127.0.0.1"
proxy_host = "127.0.0.1"
proxy_port_base = 11000
heartbeat_interval = 10
sem_cap = 3


def run_gateway():
    try:
        gateway = AgentGatewayServer(monitor_url, dbserver_url, log_level=logging.DEBUG)
        gateway.run(gateway_host, gateway_port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


def run_monitor():
    try:
        monitor = AgentMonitorServer(log_level=logging.DEBUG)
        monitor.run(monitor_host, monitor_port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


def run_dbserver():
    try:
        dbserver = AgentDatabaseServer(db_file, log_level=logging.DEBUG)
        dbserver.run(dbserver_host, dbserver_port)
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
async def test_gateway():
    try:
        if os.path.exists(db_file):
            os.remove(db_file)

        logger = AsyncLogger("pytest", level=logging.DEBUG)
        await logger.start()

        monitor_process = mp.Process(target=run_monitor)
        monitor_process.start()

        assert await is_url_ready(logger, monitor_url)

        dbserver_process = mp.Process(target=run_dbserver)
        dbserver_process.start()

        assert await is_url_ready(logger, dbserver_url)

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

        async def execute_task():
            n_rounds, n_samples, n_voters = 2, 5, 3

            task_name = "code_generation"
            task_description = "MULTITHREADED BLOCKED MATRIX MULTIPLICATION IN C++"
            data = {
                "task_name": task_name,
                "task_description": task_description,
                "n_rounds": n_rounds,
                "n_samples": n_samples,
                "n_voters": n_voters,
            }

            resp = await http_post(gateway_url + "/query", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]
            task_id = body["task_id"]

            sleep_interval = 10
            while True:
                data = {
                    "task_id": task_id,
                }
                resp = await http_get(gateway_url + "/task/status", data)
                assert resp["success"]
                body = resp["body"]

                status = body["status"]
                if status == TaskStatus.NON_EXIST:
                    error_str = f"task {task_id} not exist"
                    await logger.error(f"[Task {task_id}] {error_str}")
                    raise Exception(f"task {task_id} not exist")

                elif status == TaskStatus.PENDING:
                    await logger.warning(
                        f"[Task {task_id}] term: {body['term']} round: {body['round']} waiting for result..."
                    )
                    await random_sleep(sleep_interval)

                elif status == TaskStatus.ABORTED:
                    await logger.warning(
                        f"[Task {task_id}] term: {body['term']} round: {body['round']} aborted"
                    )
                    break

                elif status == TaskStatus.COMPLETED:
                    assert body["success"]
                    result = body["result"]
                    assert result != ""
                    await logger.debug(f"[Task {task_id}] result: \n{result}")
                    break

                else:
                    raise Exception("invalid state")

            data = {
                "task_id": task_id,
            }
            resp = await http_get(dbserver_url + "/task", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]

            assert body["term"] == 0
            assert body["round"] == n_rounds - 1
            assert body["task_name"] == task_name
            assert body["task_description"] == task_description
            assert body["task_status"] == TaskStatus.COMPLETED
            assert body["task_result"] != ""

        futures = []
        task_num = 2
        for i in range(task_num):
            futures.append(execute_task())

        await asyncio.gather(*futures)

    finally:
        os.remove(db_file)
        await logger.stop()

        monitor_process.terminate()
        gateway_process.terminate()
        dbserver_process.terminate()
        for proxy_process in proxy_processes:
            proxy_process.terminate()

        monitor_process.join()
        gateway_process.join()
        dbserver_process.join()
        for proxy_process in proxy_processes:
            proxy_process.join()
