import asyncio
import random
from contextlib import asynccontextmanager
from typing import Dict

import aiohttp
import uvicorn
from fastapi import APIRouter, FastAPI

from agentos.tasks.executor import AgentInfo
from agentos.tasks.generate_task import get_task_description
from agentos.utils.logger import AsyncLogger


def pick_random_agent(agents: Dict[str, AgentInfo]) -> AgentInfo:
    k = random.randint(0, len(agents) - 1)
    count = 0
    for id, agent_info in agents:
        if k == count:
            return agent_info
        count += 1


class RegionalGateway:
    def __init__(self, monitor_url: str):
        self.monitor_url = monitor_url
        self.task_map: Dict[int, str | None] = dict()
        self.lock = asyncio.Lock()
        self.agents: Dict[str, AgentInfo] = dict()
        self.logger = AsyncLogger("gateway")

    async def ready(self):
        return {"status": "gateway ok"}

    async def query(self, query: str, task_name: str):
        try:
            task_prompt = get_task_description(task_name, query)
            agent = pick_random_agent(self.agents)
            data = {
                "task_name": task_name,
                "task_description": task_prompt,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    agent.addr + "/coordinator", json=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"]
                    task_id = body["task_id"]
                    return {
                        "success": True,
                        "task_id": task_id,
                    }

        except Exception as e:
            return {"success": False, "reason": f"exception: {e}"}

    async def task_status(self, task_id: int):
        async with self.lock:
            if task_id not in self.task_map:
                return {
                    "status": "not exist",
                }

            task_result = self.task_map[task_id]
            if task_result is None:
                return {"status": "waiting"}
            else:
                return {
                    "status": "ok",
                    "result": task_result,
                }

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.logger.start()
        yield
        await self.logger.stop()

    def run(self, host: str, port: int):
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/task/status")(self.task_status)
        router.post("/query")(self.query)
        app = FastAPI(lifespan=self.lifespan)
        app.include_router(router)

        uvicorn.run(app, host=host, port=port)
