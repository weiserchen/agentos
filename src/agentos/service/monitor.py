import asyncio
import time
from contextlib import asynccontextmanager
from typing import Dict

import uvicorn
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from agentos.tasks.executor import AgentInfo
from agentos.utils.logger import AsyncLogger
from agentos.utils.sleep import random_sleep


class AgentStatusRequest(BaseModel):
    agent_info: AgentInfo | None


class AgentMonitorServer:
    agents: Dict[str, AgentInfo]

    def __init__(self, update_interval: int = 10):
        self.update_interval = update_interval
        self.alive_timeout = update_interval * 3
        self.agents = dict()
        self.last_update_time = dict()
        self.lock = asyncio.Lock()
        self.logger = AsyncLogger("monitor")

    async def ready(self):
        return {
            "status": "agent monitor ok",
        }

    async def get_agents(self):
        api_path = "get_agents"
        async with self.lock:
            await self.logger.info(f"{api_path} - {self.agents}")
            return {
                "agents": self.agents,
            }

    async def get_agent(self, id: str):
        async with self.lock:
            return {
                "agent_info": self.agents.get(id),
            }

    async def add_agent(self, req: AgentStatusRequest):
        api_path = "add_agent"
        await self.logger.info(f"{api_path} - {req}")
        now = time.time()
        async with self.lock:
            id = req.agent_info.id
            if req.agent_info is None:
                return {
                    "success": False,
                }

            self.agents[id] = req.agent_info
            self.last_update_time[id] = now
            return {
                "success": True,
                "members": self.agents,
            }

    async def delete_agent(self, id: str):
        api_path = "delete_agent"
        await self.logger.info(f"{api_path} - {id}")
        async with self.lock:
            if id not in self.agents:
                return {
                    "success": False,
                }

            del self.agents[id]
            return {
                "success": True,
            }

    async def remove_dead_member(self):
        while True:
            now = time.time()
            async with self.lock:
                dead_agents = []
                for id in self.agents.keys():
                    if now - self.last_update_time[id] >= self.alive_timeout:
                        dead_agents.append(id)

                for id in dead_agents:
                    del self.agents[id]

            await random_sleep(self.update_interval)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.logger.start()
        asyncio.create_task(self.remove_dead_member())
        yield
        await self.logger.stop()

    def run(self, host: str, port: int):
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/agent")(self.get_agent)
        router.post("/agent")(self.add_agent)
        router.delete("/agent/{id}")(self.delete_agent)
        router.get("/agent/list")(self.get_agents)
        app = FastAPI(lifespan=self.lifespan)
        app.include_router(router)

        uvicorn.run(app, host=host, port=port, log_level="warning")
