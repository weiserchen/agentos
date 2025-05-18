from fastapi import APIRouter, FastAPI, Query
from pydantic import BaseModel
from typing import Dict
import asyncio
import uvicorn

class AgentInfo(BaseModel):
    addr: str = Query(...)
    workload: int = Query(...)

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
                "agents": list(self.agents.values())
            }
    
    async def get_agent(self, addr: str):
        async with self.lock:
            return {
                "agent_info": self.agents.get(addr)
            }
        
    async def add_agent(self, req: AgentStatusRequest):
        async with self.lock:
            addr = req.agent_info.addr
            if req.agent_info is None:
                return {
                    "success": False
                }
            
            self.agents[addr] = req.agent_info
            return {
                "success": True
            }
    
    async def delete_agent(self, agent_addr: str):
        async with self.lock:
            if agent_addr not in self.agents:
                return {
                    "success": False
                }
            
            del self.agents[agent_addr]
            return {
                "success": True
            }
        
    def run(self, host: str, port: int):
        app = FastAPI()
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/agent")(self.get_agent)
        router.post("/agent")(self.add_agent)
        router.delete("/agent/{agent_addr:path}")(self.delete_agent)
        router.get("/agent/list")(self.get_agents)
        app.include_router(router)
        uvicorn.run(app, host=host, port=port)