import logging
import multiprocessing as mp

import pytest

from agentos.service.monitor import AgentMonitorServer
from agentos.tasks.utils import http_delete, http_get, http_post
from agentos.utils.logger import AsyncLogger
from agentos.utils.ready import is_url_ready

monitor = AgentMonitorServer(log_level=logging.DEBUG)
monitor_host = "127.0.0.1"
monitor_port = 10001
monitor_url = f"http://{monitor_host}:{monitor_port}"


def run_monitor():
    monitor.run(monitor_host, monitor_port)


@pytest.mark.asyncio
async def test_agent_monitor():
    try:
        logger = AsyncLogger("pytest", level=logging.DEBUG)
        await logger.start()

        monitor_process = mp.Process(target=run_monitor)
        monitor_process.start()

        assert await is_url_ready(logger, monitor_url)

        resp = await http_get(monitor_url + "/agent/list")
        assert resp["success"]
        body = resp["body"]
        assert body["success"]
        agents = body["agents"]
        assert len(agents) == 0

        params = {"id": "non-exist-agent"}
        resp = await http_get(monitor_url + "/agent", params)
        assert resp["success"]
        body = resp["body"]
        assert body["success"]
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
            resp = await http_post(monitor_url + "/agent", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"]

        for i in range(agents_num):
            agent_id = agent_ids[i]
            agent_addr = agent_addrs[i]
            agent_workload = agent_workloads[i]
            params = {"id": agent_id}
            resp = await http_get(monitor_url + "/agent", params)
            assert resp["success"]
            body = resp["body"]
            assert body["success"]

            agent_info = body["agent_info"]
            assert agent_info is not None
            assert agent_info["id"] == agent_id
            assert agent_info["addr"] == agent_addr
            assert agent_info["workload"] == agent_workload

        resp = await http_get(monitor_url + "/agent/list")
        body = resp["body"]
        assert body["success"]

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
            resp = await http_delete(f"{monitor_url}/agent/{agent_id}")
            assert resp["success"]
            body = resp["body"]
            assert body["success"]

        resp = await http_get(monitor_url + "/agent/list")
        assert resp["success"]
        body = resp["body"]
        assert body["success"]

        agents = body["agents"]
        assert len(agents) == int(agents_num / 2)

        for deleted_id in deleted_ids:
            assert deleted_id not in agents

    finally:
        await logger.stop()
        monitor_process.terminate()
        monitor_process.join()
