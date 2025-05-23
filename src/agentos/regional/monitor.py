from fastapi import APIRouter, FastAPI, Query
from pydantic import BaseModel
from typing import Dict
from agentos.tasks.executor import AgentInfo
import asyncio
import uvicorn
from uvicorn import Server, Config


class AgentStatusRequest(BaseModel):
    agent_info: AgentInfo | None

class RegionalAgentMonitor:
    agents: Dict[str, AgentInfo]

    def __init__(self):
        self.agents = dict()
        self.lock = asyncio.Lock()

    async def ready(self):
        return {
            "status": "agent monitor ok"
        }

    async def get_agents(self):
        async with self.lock:
            return {
                "agents": self.agents,
            }
    
    async def get_agent(self, id: str):
        async with self.lock:
            return {
                "agent_info": self.agents.get(id)
            }
        
    async def add_agent(self, req: AgentStatusRequest):
        async with self.lock:
            print(req)
            id = req.agent_info.id
            if req.agent_info is None:
                return {
                    "success": False
                }
            
            self.agents[id] = req.agent_info
            return {
                "success": True,
                "members": self.agents,
            }
    
    async def delete_agent(self, id: str):
        async with self.lock:
            if id not in self.agents:
                return {
                    "success": False
                }
            
            del self.agents[id]
            return {
                "success": True
            }
        
    def run(self, host: str, port: int):
        app = FastAPI()
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/agent")(self.get_agent)
        router.post("/agent")(self.add_agent)
        router.delete("/agent/{id}")(self.delete_agent)
        router.get("/agent/list")(self.get_agents)
        app.include_router(router)
        uvicorn.run(app, host=host, port=port)
        # config = Config(app=app, host=host, port=port)
        # server = Server(config)
        # server.run()