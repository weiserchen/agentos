import asyncio
import random
import sys
import traceback
from contextlib import asynccontextmanager
from typing import Dict

import aiohttp
import uvicorn
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from agentos.tasks.elem import TaskStatus
from agentos.tasks.executor import AgentInfo
from agentos.tasks.utils import http_post_with_exception
from agentos.utils.logger import AsyncLogger
from agentos.utils.sleep import random_sleep


class AgentStatusRequest(BaseModel):
    agent_info: AgentInfo | None


class AgentRecoveryServer:
    agents: Dict[str, AgentInfo]

    def __init__(self, monitor_url: str, dbserver_url: str, update_interval: int = 10):
        self.monitor_url = monitor_url
        self.dbserver_url = dbserver_url
        self.update_interval = update_interval
        self.agents = dict()
        self.recovering_set = set()
        self.lock = asyncio.Lock()
        self.logger = AsyncLogger("recovery")

    async def ready(self):
        return {
            "status": "agent recovery ok",
        }

    async def get_agent(self) -> AgentInfo:
        async with self.lock:
            agent_list = list(self.agents.values())
            return random.choice(agent_list)

    async def recover_agent(self, agent: AgentInfo):
        MAX_RETRY = 3

        async def recover_task(task) -> bool:
            task["term"] += 1
            task["round"] += 1
            task_id = task["task_id"]
            round = task["round"]
            term = task["term"]
            task_name = task["task_name"]
            task_description = task["task_description"]
            task_result = task["task_result"]
            data = {
                "task_id": task_id,
                "round": round,
                "term": term,
                "task_name": task_name,
                "task_description": task_description,
                "task_result": task_result,
            }
            await self.logger.warning(f"recoverying task {task_id}")
            for i in range(MAX_RETRY):
                try:
                    new_agent = await self.get_agent()
                    await http_post_with_exception(
                        url=new_agent.addr + "/coordinator",
                        data=data,
                        name="recovery",
                    )

                    await self.logger.warning(f"[Task {task_id}] recovered")

                    return True

                except Exception as e:
                    if i == MAX_RETRY - 1:
                        await self.logger.error(
                            f"recover_agents - failed to retry task: {task_id} - exception: {e}"
                        )
                        return False
                    else:
                        await self.logger.error(
                            f"recover_agents - retrying task: {task_id} - exception: {e}"
                        )
                        await random_sleep(5)

        try:
            await self.logger.warning(f"recovering agent {agent.id}...")

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
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.put(
                                self.dbserver_url + "/task/status", json=data
                            ) as response:
                                assert response.status < 300, (
                                    f"error response status code: {response.status}"
                                )
                                body = await response.json()
                                assert body["success"], body["err"]

                        await self.logger.warning(f"[Task {task['task_id']}] aborted")

                    except Exception as e:
                        await self.logger.error(f"recover_agents - exception: {e}")

            async with self.lock:
                self.recovering_set.remove(agent.id)

        except Exception as e:
            tb = sys.exc_info()[2]
            filename, lineno, func, text = traceback.extract_tb(tb)[-1]
            err_str = f"Exception in {filename}, line {lineno}: {text}"
            await self.logger.error(f"recover_agents - exception: {e} - {err_str}")

        finally:
            async with self.lock:
                self.recovering_set.discard(agent.id)

    async def update_membership(self):
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

                        await self.logger.debug(f"update_membership: {new_agents}")
                        async with self.lock:
                            for id, agent in self.agents.items():
                                if id not in new_agents:
                                    if id not in self.recovering_set:
                                        self.recovering_set.add(id)
                                        asyncio.create_task(self.recover_agent(agent))

                            self.agents = new_agents

            except Exception as e:
                await self.logger.error(f"update_membership - exception: {e}")

            await random_sleep(self.update_interval)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.logger.start()
        asyncio.create_task(self.update_membership())
        yield
        await self.logger.stop()

    def run(self, host: str, port: int):
        router = APIRouter()
        router.get("/ready")(self.ready)
        app = FastAPI(lifespan=self.lifespan)
        app.include_router(router)

        uvicorn.run(app, host=host, port=port)
