import pytest
import asyncio
import json
import aiohttp
import multiprocessing
import urllib
from agentos.regional.monitor import RegionalAgentMonitor
from typing import List

@pytest.mark.asyncio
async def test_agent_monitor():
    monitor = RegionalAgentMonitor()
    monitor_host = "127.0.0.1"
    monitor_port = 10001
    monitor_url = f'http://{monitor_host}:{monitor_port}'

    def run_monitor():
        monitor.run(monitor_host, monitor_port)

    monitor_process = multiprocessing.Process(target=run_monitor)
    monitor_process.start()

    try: 
        MAX_RETRY = 10
        async with aiohttp.ClientSession() as session:
            for i in range(MAX_RETRY):
                try:
                    async with session.get(monitor_url+"/ready") as response:
                        assert response.status < 300
                        break
                except aiohttp.ClientConnectionError as e:
                    if i == MAX_RETRY - 1:
                        raise e
                    else:
                        await asyncio.sleep(0.5)

            async with session.get(monitor_url+"/agent/list") as response:
                assert response.status < 300
                body = await response.json()
                agents = body['agents']
                assert len(agents) == 0

            params = [('addr', 'http://non-exist-agent')]
            async with session.get(monitor_url+"/agent", params=params) as response:
                assert response.status < 300
                body = await response.json()
                agent_info = body['agent_info']
                assert agent_info is None

            agents_num = 10
            for i in range(agents_num):
                agent_addr = f"http://agent-{i+1}"
                agent_workload = (i+1) * 10
                data = {
                    "agent_info": {
                        "addr": agent_addr,
                        "workload": agent_workload,
                    },
                }
                async with session.post(monitor_url+"/agent", json=data) as response:
                    assert response.status < 300
                    body = await response.json()
                    success = body['success']
                    assert success == True

            for i in range(agents_num):
                agent_addr = f"http://agent-{i+1}"
                agent_workload = (i+1) * 10
                params = [('addr', agent_addr)]
                async with session.get(monitor_url+"/agent", params=params) as response:
                    assert response.status < 300
                    body = await response.json()
                    agent_info = body['agent_info']
                    assert agent_info is not None
                    assert agent_info['addr'] == agent_addr
                    assert agent_info['workload'] == agent_workload

            async with session.get(monitor_url+"/agent/list") as response:
                assert response.status < 300
                body = await response.json()
                agents = body['agents']
                assert len(agents) == 10

                agents_addrs = []
                agents_workloads = []
                for i in range(agents_num):
                    agent_addr = f"http://agent-{i+1}"
                    agent_workload = (i+1) * 10
                    agents_addrs.append(agent_addr)
                    agents_workloads.append(agent_workload)

                for i, agent in enumerate(agents):
                    idx = -1
                    try:
                        idx = agents_addrs.index(agent['addr'])
                    except Exception:
                        pass

                    assert idx != -1
                    assert agent['workload'] == agents_workloads[i]

            for i in range(0, agents_num, 2):
                agent_addr = f"http://agent-{i+1}"
                encoded_addr = urllib.parse.quote(agent_addr, safe="")
                async with session.delete(f'{monitor_url}/agent/{encoded_addr}') as response:
                    assert response.status < 300
                    body = await response.json()
                    success = body['success']
                    assert success == True

            async with session.get(monitor_url+"/agent/list") as response:
                assert response.status < 300
                body = await response.json()
                agents = body['agents']
                assert len(agents) == int(agents_num / 2)

                agents_addrs = []
                agents_workloads = []
                for i in range(1, agents_num, 2):
                    agent_addr = f"http://agent-{i+1}"
                    agent_workload = (i+1) * 10
                    agents_addrs.append(agent_addr)
                    agents_workloads.append(agent_workload)

                for i, agent in enumerate(agents):
                    idx = -1
                    try:
                        idx = agents_addrs.index(agent['addr'])
                    except Exception:
                        pass

                    assert idx != -1
                    assert agent['workload'] == agents_workloads[i]
            
            
    finally:
        monitor_process.terminate()
        monitor_process.join()

