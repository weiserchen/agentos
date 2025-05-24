import asyncio
from contextlib import asynccontextmanager
from typing import Dict

import uvicorn
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from agentos.tasks.executor import AgentInfo
from agentos.utils.logger import AsyncLogger


class AgentStatusRequest(BaseModel):
    agent_info: AgentInfo | None


class RegionalAgentMonitor:
    agents: Dict[str, AgentInfo]

    def __init__(self):
        self.agents = dict()
        self.lock = asyncio.Lock()
        self.logger = AsyncLogger("monitor")

    async def ready(self):
        return {"status": "agent monitor ok"}

    async def get_agents(self):
        async with self.lock:
            return {
                "agents": self.agents,
            }

    async def get_agent(self, id: str):
        async with self.lock:
            return {"agent_info": self.agents.get(id)}

    async def add_agent(self, req: AgentStatusRequest):
        api_path = "add_agent"
        await self.logger.info(f"{api_path} - {req}")
        async with self.lock:
            id = req.agent_info.id
            if req.agent_info is None:
                return {"success": False}

            self.agents[id] = req.agent_info
            return {
                "success": True,
                "members": self.agents,
            }

    async def delete_agent(self, id: str):
        api_path = "delete_agent"
        await self.logger.info(f"{api_path} - {id}")
        async with self.lock:
            if id not in self.agents:
                return {"success": False}

            del self.agents[id]
            return {"success": True}

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.logger.start()
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

        uvicorn.run(app, host=host, port=port)
