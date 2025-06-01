import asyncio
import multiprocessing as mp
import os
from multiprocessing import Process
from typing import List

from agentos.agent.proxy import AgentInfo, AgentProxy
from agentos.service.dbserver import AgentDatabaseServer
from agentos.service.gateway import AgentGatewayServer
from agentos.service.monitor import AgentMonitorServer
from agentos.utils.logger import AsyncLogger
from agentos.utils.ready import is_url_ready

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
local_api_port_base = 8000
heartbeat_interval = 10
sem_cap = 3


def run_gateway():
    try:
        gateway = AgentGatewayServer(monitor_url, dbserver_url)
        gateway.run(gateway_host, gateway_port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


def run_monitor():
    try:
        monitor = AgentMonitorServer()
        monitor.run(monitor_host, monitor_port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


def run_dbserver():
    try:
        dbserver = AgentDatabaseServer(db_file)
        dbserver.run(dbserver_host, dbserver_port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


def run_proxy(id: str, domain: str, host: str, port: int, local_api_port: int):
    try:
        proxy = AgentProxy(
            id,
            gateway_url,
            monitor_url,
            dbserver_url,
            local_api_port=local_api_port,
            update_interval=heartbeat_interval,
            sem_cap=sem_cap,
        )
        proxy.run(domain, host, port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


async def main():
    try:
        logger = AsyncLogger("service")
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
        proxies_num = 4
        for i in range(proxies_num):
            proxy_id = f"agent-{i}"
            proxy_port = proxy_port_base + i
            local_api_port = local_api_port_base + i
            proxy_url = f"http://{proxy_host}:{proxy_port_base + i}"
            proxy_process = mp.Process(
                target=run_proxy,
                args=(proxy_id, proxy_domain, proxy_host, proxy_port, local_api_port),
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

        await logger.info("All service started.")

        while True:
            await asyncio.sleep(10)

    except KeyboardInterrupt:
        await logger.info("KeyboardInterrupt caught. Shutting down gracefully.")

    finally:
        await logger.stop()

        monitor_process.terminate()
        dbserver_process.terminate()
        gateway_process.terminate()
        for proxy_process in proxy_processes:
            proxy_process.terminate()

        monitor_process.join()
        dbserver_process.join()
        gateway_process.join()
        for proxy_process in proxy_processes:
            proxy_process.join()


if __name__ == "__main__":
    asyncio.run(main())
