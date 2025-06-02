import asyncio
import random
from contextlib import asynccontextmanager
from typing import Dict

import aiohttp
import uvicorn
from fastapi import APIRouter, FastAPI

from agentos.tasks.elem import TaskCompleteEvent, TaskQueryEvent
from agentos.tasks.executor import AgentInfo
from agentos.utils.logger import AsyncLogger


def pick_random_agent(agents: Dict[str, AgentInfo]) -> AgentInfo:
    agent_list = list(agents.values())
    return random.choice(agent_list)


class TaskResult:
    def __init__(self, task_id: int):
        self.task_id = task_id
        self.completed = False
        self.success = False
        self.result = ""

    def mark_complete(self, success: bool, result: str):
        self.completed = True
        self.success = success
        self.result = result


class RegionalGateway:
    def __init__(self, monitor_url: str):
        self.monitor_url = monitor_url
        self.task_map: Dict[int, TaskResult] = dict()
        self.lock = asyncio.Lock()
        self.agents: Dict[str, AgentInfo] = dict()
        self.logger = AsyncLogger("gateway")
        self.lock = asyncio.Lock()
        self.task_counter = 1

    async def ready(self):
        return {
            "status": "gateway ok",
        }

    async def query(self, e: TaskQueryEvent):
        try:
            # replace with db insertion
            task_id = None
            async with self.lock:
                task_id = self.task_counter
                self.task_counter += 1

            agent = pick_random_agent(self.agents)
            data = {
                "task_id": task_id,
                "task_name": e.task_name,
                "task_description": e.task_description,
            }
            await self.logger.debug(f"query - {data}")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    agent.addr + "/coordinator", json=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"]
                    self.task_map[task_id] = TaskResult(task_id)
                    return {
                        "success": True,
                        "task_id": task_id,
                    }

        except Exception as err:
            await self.logger.error(f"query - exception: {err}")
            return {
                "success": False,
            }

    async def task_update(self, e: TaskCompleteEvent):
        async with self.lock:
            if e.task_id not in self.task_map:
                return {
                    "success": False,
                }

            self.task_map[e.task_id].mark_complete(e.success, e.result)
            return {
                "success": True,
            }

    async def task_status(self, task_id: int):
        async with self.lock:
            if task_id not in self.task_map:
                return {
                    "status": "not exist",
                }

            task_result = self.task_map[task_id]
            if not task_result.completed:
                return {
                    "status": "waiting",
                }
            else:
                return {
                    "status": "ok",
                    "success": task_result.success,
                    "result": task_result.result,
                }

    async def retrieve_agents(self):
        sleep_interval = 10
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
                        async with self.lock:
                            self.agents = new_agents

                await asyncio.sleep(sleep_interval)

            except Exception as e:
                await self.logger.error(f"retrieve_agents - exception: {e}")

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        asyncio.create_task(self.retrieve_agents())
        await self.logger.start()
        yield
        await self.logger.stop()

    def run(self, host: str, port: int):
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/task/status")(self.task_status)
        router.post("/query")(self.query)
        router.post("/task/update")(self.task_update)
        app = FastAPI(lifespan=self.lifespan)
        app.include_router(router)
        uvicorn.run(app, host=host, port=port, log_level="warning")
