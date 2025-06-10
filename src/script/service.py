import asyncio
import multiprocessing as mp
import os
from multiprocessing import Process
from typing import List
import random
import signal 

from agentos.agent.proxy import AgentInfo, AgentProxy
from agentos.service.dbserver import AgentDatabaseServer
from agentos.service.gateway import AgentGatewayServer
from agentos.service.monitor import AgentMonitorServer
from agentos.service.recovery import AgentRecoveryServer
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

recovery_host = "127.0.0.1"
recovery_port = 10003
recovery_url = f"http://{recovery_host}:{recovery_port}"
recovery_interval = 2

proxy_domain = "127.0.0.1"
proxy_host = "127.0.0.1"

proxy_port_base = 11000
local_api_port_base = 8000

num_proxies = 4
heartbeat_interval = 2
sem_cap = 10
queue_cap = 1000
load_balancing = "least_loaded"  # Options: "random", "least_loaded"
scheduling_policy = "srtf"  # Options: "fifo", "arrival_priority", "sjf", "srtf"
voting_strategy = "early_majority"  # Options: "naive", "early_majority"

enable_failures       = True     
mean_failure_interval = 30
mean_down_time        = 10

def run_gateway():
    try:
        gateway = AgentGatewayServer(monitor_url, dbserver_url)
        gateway.run(gateway_host, gateway_port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e


def run_monitor():
    try:
        monitor = AgentMonitorServer(update_interval=heartbeat_interval)
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


def run_recovery():
    try:
        recovery = AgentRecoveryServer(
            monitor_url,
            dbserver_url,
            update_interval=recovery_interval,
        )
        recovery.run(recovery_host, recovery_port)
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
            queue_cap=queue_cap,
            sem_cap=sem_cap,
            load_balancing=load_balancing,
            scheduling_policy=scheduling_policy,
            voting_strategy=voting_strategy,
        )
        proxy.run(domain, host, port)
    except Exception as e:
        print(f"Exception: {e}")
        raise e
    
async def _simulate_proxy_failures(logger: AsyncLogger, proxy_map: dict[str, Process], proxy_creation_args: dict[str, dict]):
    """
    Injects crash-and-restart failures. This coroutine repeatedly:
      1. Waits for a healthy period.
      2. Picks a random live proxy and hard-kills it (crash).
      3. Waits for a downtime period.
      4. Relaunches the killed proxy (restart as a fresh instance).
    """
    await logger.warning(
        f"Crash-and-Restart injector enabled. Mean Failure Interval: {mean_failure_interval}s, Mean downtime: {mean_down_time}s"
    )

    while enable_failures:
        # failure_interval = random.expovariate(1 / mean_failure_interval)
        failure_interval = mean_failure_interval
        await logger.warning(f"[FAILURE INJECTION] Next failure in {round(failure_interval)}s")
        await asyncio.sleep(failure_interval)

        live_proxy_ids = [pid for pid, p in proxy_map.items() if p.is_alive()]
        if not live_proxy_ids:
            await logger.warning("[FAILURE INJECTION] All proxies are dead. Stopping injector.")
            return

        victim_id = random.choice(live_proxy_ids)
        victim_process = proxy_map[victim_id]
        
        await logger.warning(f"[FAILURE INJECTION] CRASHING proxy {victim_id})")
        try:
            if os.name == "posix":
                os.kill(victim_process.pid, signal.SIGKILL)
            else:
                raise NotImplementedError("Process killing not implemented for this OS")
        except ProcessLookupError:
            await logger.warning(f"[FAILURE INJECTION] Proxy {victim_process.name} exited before it could be killed.")

        # down_time = random.expovariate(1 / mean_down_time)
        down_time = mean_down_time
        await logger.warning(f"[FAILURE INJECTION] Proxy {victim_id} is down. Waiting {round(down_time)}s to restart.")
        await asyncio.sleep(down_time)

        await logger.warning(f"[FAILURE INJECTION] RESTARTING proxy {victim_id}...")
        
        creation_args = proxy_creation_args[victim_id]
        new_proxy_process = mp.Process(
            target=run_proxy,
            name=victim_id,
            args=creation_args['args']
        )
        new_proxy_process.start()

        proxy_map[victim_id] = new_proxy_process

        proxy_url = creation_args['url']
        if not await is_url_ready(logger, proxy_url):
            await logger.error(f"[FAILURE INJECTION] Restarted proxy {victim_id} failed to become ready.")

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

        recovery_process = mp.Process(target=run_recovery)
        recovery_process.start()

        assert await is_url_ready(logger, recovery_url)

        proxy_map: dict[str, Process] = {}
        proxy_creation_args: dict[str, dict] = {}
        proxy_processes: List[Process] = []
        proxy_ids = []
        proxy_urls = []
        proxies = dict()
        for i in range(num_proxies):
            proxy_id = f"agent-{i}"
            proxy_port = proxy_port_base + i
            local_api_port = local_api_port_base + i
            proxy_url = f"http://{proxy_host}:{proxy_port_base + i}"

            args = (proxy_id, proxy_domain, proxy_host, proxy_port, local_api_port)
            proxy_process = mp.Process(
                target=run_proxy, args=args,
            )
            proxies[proxy_id] = AgentInfo(
                id=proxy_id, addr=proxy_url, workload=0,
            )
            proxy_ids.append(proxy_id)
            proxy_urls.append(proxy_url)
            proxy_processes.append(proxy_process)
            proxy_creation_args[proxy_id] = {'args': args, 'url': proxy_url}
            proxy_map[proxy_id] = proxy_process

            proxy_process.start()

        for proxy_url in proxy_urls:
            assert await is_url_ready(logger, proxy_url)

        gateway_process = mp.Process(target=run_gateway)
        gateway_process.start()

        assert await is_url_ready(logger, gateway_url)

        if enable_failures:
            asyncio.create_task(
                _simulate_proxy_failures(logger, proxy_map, proxy_creation_args)
            )

        await logger.info("All service started.")

        while True:
            await asyncio.sleep(10)

    except KeyboardInterrupt:
        await logger.info("KeyboardInterrupt caught. Shutting down gracefully.")

    finally:
        await logger.stop()

        monitor_process.terminate()
        dbserver_process.terminate()
        recovery_process.terminate()
        gateway_process.terminate()
        for proxy_process in proxy_processes:
            proxy_process.terminate()

        monitor_process.join()
        dbserver_process.join()
        recovery_process.join()
        gateway_process.join()
        for proxy_process in proxy_processes:
            proxy_process.join()


if __name__ == "__main__":
    asyncio.run(main())
