import logging
import multiprocessing as mp

import pytest

from agentos.agent.proxy import AgentProxy
from agentos.service.monitor import AgentMonitorServer
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

dbserver_host = "127.0.0.1"
dbserver_port = 10002
dbserver_url = f"http://{dbserver_host}:{dbserver_port}"

proxy_domain = "127.0.0.1"
proxy_host = "127.0.0.1"
proxy_port = 11000
proxy_id = "agent-0"
proxy_url = f"http://{proxy_host}:{proxy_port}"
heartbeat_interval = 5


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
            log_level=logging.DEBUG,
        )
        proxy.run(domain, host, port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


@pytest.mark.asyncio
async def test_agent_proxy():
    try:
        logger = AsyncLogger("pytest", level=logging.DEBUG)
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

        for _ in range(MAX_RETRY):
            resp = await http_get(proxy_url + "/membership/view")
            body = resp["body"]
            agents = body["agents"]
            await logger.info(f"agents: {agents}")
            if len(agents) == 1:
                view_ok = True
                break

            await random_sleep(0.5)

        assert view_ok

        data = {
            "task_id": 1,
            "task_round": 0,
            "task_action": "generation",
            "task_description": "A travel plan to Irvine",
            "task_stop": None,
            "n_samples": 5,
            "n_voters": 3,
            "total_rounds": 2,
            "total_llm_calls": 16,
        }
        resp = await http_post(proxy_url + "/agent/call", data)
        assert resp["success"]
        body = resp["body"]
        result = body["result"]
        await logger.info(f"Result: \n{result}")

    finally:
        await logger.stop()

        monitor_process.terminate()
        monitor_process.join()

        proxy_process.terminate()
        proxy_process.join()
