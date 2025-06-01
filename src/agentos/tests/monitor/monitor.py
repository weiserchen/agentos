import multiprocessing as mp

import aiohttp
import pytest

from agentos.service.monitor import AgentMonitorServer
from agentos.utils.logger import AsyncLogger
from agentos.utils.ready import is_url_ready

monitor = AgentMonitorServer()
monitor_host = "127.0.0.1"
monitor_port = 10001
monitor_url = f"http://{monitor_host}:{monitor_port}"


def run_monitor():
    monitor.run(monitor_host, monitor_port)


@pytest.mark.asyncio
async def test_agent_monitor():
    try:
        logger = AsyncLogger("pytest")
        await logger.start()

        monitor_process = mp.Process(target=run_monitor)
        monitor_process.start()

        assert await is_url_ready(logger, monitor_url)

        async with aiohttp.ClientSession() as session:
            async with session.get(monitor_url + "/agent/list") as response:
                assert response.status < 300
                body = await response.json()
                agents = body["agents"]
                assert len(agents) == 0

            params = {"id": "non-exist-agent"}
            async with session.get(monitor_url + "/agent", params=params) as response:
                assert response.status < 300
                body = await response.json()
                agent_info = body["agent_info"]
                assert agent_info is None

            agents_num = 10
            agent_ids = []
            agent_addrs = []
            agent_workloads = []
            for i in range(agents_num):
                agent_id = f"agent-{i}"
                agent_addr = f"http://agent-{i}"
                agent_workload = (i + 1) * 10
                agent_ids.append(agent_id)
                agent_addrs.append(agent_addr)
                agent_workloads.append(agent_workload)
                data = {
                    "agent_info": {
                        "id": agent_id,
                        "addr": agent_addr,
                        "workload": agent_workload,
                    },
                }
                async with session.post(monitor_url + "/agent", json=data) as response:
                    assert response.status < 300
                    body = await response.json()
                    success = body["success"]
                    assert success

            for i in range(agents_num):
                agent_id = agent_ids[i]
                agent_addr = agent_addrs[i]
                agent_workload = agent_workloads[i]
                params = {"id": agent_id}
                async with session.get(
                    monitor_url + "/agent", params=params
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    agent_info = body["agent_info"]
                    assert agent_info is not None
                    assert agent_info["id"] == agent_id
                    assert agent_info["addr"] == agent_addr
                    assert agent_info["workload"] == agent_workload

            async with session.get(monitor_url + "/agent/list") as response:
                assert response.status < 300
                body = await response.json()
                agents = body["agents"]
                assert len(agents) == 10

                for i in range(agents_num):
                    agent_id = agent_ids[i]
                    agent_addr = agent_addrs[i]
                    agent_workload = agent_workloads[i]
                    assert agent_id in agents
                    agent = agents[agent_id]
                    assert agent["id"] == agent_id
                    assert agent["addr"] == agent_addr
                    assert agent["workload"] == agent_workload

            deleted_ids = []
            for i in range(0, agents_num, 2):
                agent_id = agent_ids[i]
                deleted_ids.append(agent_id)
                async with session.delete(
                    f"{monitor_url}/agent/{agent_id}"
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    success = body["success"]
                    assert success

            async with session.get(monitor_url + "/agent/list") as response:
                assert response.status < 300
                body = await response.json()
                agents = body["agents"]
                assert len(agents) == int(agents_num / 2)

                for deleted_id in deleted_ids:
                    assert deleted_id not in agents

    finally:
        await logger.stop()
        monitor_process.terminate()
        monitor_process.join()
