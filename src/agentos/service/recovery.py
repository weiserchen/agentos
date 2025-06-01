import asyncio
import random
import time
from contextlib import asynccontextmanager
from typing import Dict

import aiohttp
import uvicorn
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from agentos.tasks.elem import TaskStatus
from agentos.tasks.executor import AgentInfo
from agentos.utils.logger import AsyncLogger


class AgentStatusRequest(BaseModel):
    agent_info: AgentInfo | None


class AgentRecoveryServer:
    agents: Dict[str, AgentInfo]

    def __init__(self, monitor_url: str, dbserver_url, update_interval: int = 5):
        self.monitor_url = monitor_url
        self.dbserver_url = dbserver_url
        self.update_interval = update_interval
        self.recovery_timeout = update_interval * 3
        self.agents = dict()
        self.membership = dict()
        self.last_update_time: Dict[str, int] = dict()
        self.recovering_set = set()
        self.lock = asyncio.Lock()
        self.logger = AsyncLogger("recovery")

    async def ready(self):
        return {"status": "agent recovery ok"}

    async def get_agent(self) -> AgentInfo:
        async with self.lock:
            agent_list = self.agents.values()
            return random.choice(agent_list)

    async def recover_agent(self, agent: AgentInfo):
        MAX_RETRY = 3

        async def recover_task(task) -> bool:
            task_id = task["task_id"]
            round = task["round"]
            term = task["term"] + 1
            task_result = task["result"]
            task_name = task["task_name"]
            task_description = task["description"]
            data = {
                "task_id": task_id,
                "round": round,
                "term": term,
                "task_result": task_result,
                "task_name": task_name,
                "task_description": task_description,
            }
            for i in range(MAX_RETRY):
                try:
                    new_agent = await self.get_agent()
                    async with session.post(
                        new_agent.addr + "/coordinator", json=data
                    ) as response:
                        assert response.status < 300, (
                            f"error response status code: {response.status}"
                        )
                        body = await response.json()
                        assert body["success"], "request not successful"
                        break
                except Exception as e:
                    if i == MAX_RETRY - 1:
                        await self.logger.error(
                            f"recover_agents - failed to retry task: {task_id} - exception: {e}"
                        )
                        return
                    else:
                        await self.logger.warning(
                            f"recover_agents - retrying task: {task_id} - exception: {e}"
                        )
                        await asyncio.sleep(0.5)

        try:
            tasks = []
            data = {
                "task_agent": agent.id,
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.dbserver_url + "/tasks/agent", params=data
                ) as response:
                    assert response.status < 300, (
                        f"error response status code: {response.status}"
                    )
                    body = await response.json()
                    assert body["success"], body["err"]
                    tasks = body["tasks"]

            futures = []
            for task in tasks:
                futures.append(recover_task(task))

            outputs = await asyncio.gather(*futures)

            for i, ok in enumerate(outputs):
                if not ok:
                    task = tasks[i]
                    data = {
                        "task_id": task["task_id"],
                        "round": -1,
                        "term": task["term"],
                        "task_status": TaskStatus.ABORTED,
                        "task_result": "aborted",
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.put(
                            self.dbserver_url + "/task/status", json=data
                        ) as response:
                            assert response.status < 300, (
                                f"error response status code: {response.status}"
                            )
                            body = await response.json()
                            assert body["success"], body["err"]

            async with self.lock:
                self.recovering_set.remove(agent.id)
                del self.membership[id]

        except Exception:
            await self.logger.error("recover_agents - exception: {e}")

    async def handle_recovery(self):
        while True:
            now = time.time()
            async with self.lock:
                for id, agent in self.membership.items():
                    last_time = self.last_update_time[id]
                    if now - last_time >= self.recovery_timeout:
                        if id not in self.recovering_set:
                            self.recovering_set.add(id)
                            asyncio.create_task(self.recover_agent(agent))

            await asyncio.sleep(self.update_interval)

    async def retrieve_agents(self):
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self.monitor_url + "/agent/list"
                    ) as response:
                        assert response.status < 300
                        body = await response.json()
                        agents = body["agents"]
                        new_agents = dict()
                        for id, agent in agents.items():
                            agent_info = AgentInfo(
                                id=id,
                                addr=agent["addr"],
                                workload=agent["workload"],
                            )
                            new_agents[id] = agent_info

                        await self.logger.debug(f"retrieve_agents: {new_agents}")
                        now = time.time()
                        async with self.lock:
                            for id, agent in new_agents:
                                self.membership[id] = agent
                                self.last_update_time[id] = now

                            self.agents = new_agents

                await asyncio.sleep(self.update_interval)

            except Exception as e:
                await self.logger.error(f"retrieve_agents - exception: {e}")

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.logger.start()
        asyncio.create_task(self.retrieve_agents)
        asyncio.create_task(self.handle_recovery)
        yield
        await self.logger.stop()

    def run(self, host: str, port: int):
        router = APIRouter()
        router.get("/ready")(self.ready)
        app = FastAPI(lifespan=self.lifespan)
        app.include_router(router)

        uvicorn.run(app, host=host, port=port)
