from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from typing import List, Dict
import multiprocessing
import asyncio
import uvicorn

class AgentInfo(BaseModel):
    id: str
    addr: str
    info_type: str
    workload: int = 0
    queue_size: int = 0

class AgentStatusRequest(BaseModel):
    agent_id: str
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
                "agents": list(self.agents.keys())
            }
    
    async def get_agent(self, agent_id: str):
        async with self.lock:
            return {
                "agent_info": self.agents.get(agent_id)
            }
    
    async def add_agent(self, req: AgentStatusRequest):
        async with self.lock:
            if req.agent_id in self.agents or req.agent_info is None:
                return {
                    "result": False
                }
            
            self.agents[req.agent_id] = req.agent_info
            return {
                "result": True
            }
    
    async def delete_agent(self, req: AgentStatusRequest):
        async with self.lock:
            if req.agent_id not in self.agents:
                return {
                    "result": False
                }
            
            del self.agents[req.agent_id]
            return {
                "result": True
            }
        
    async def update_agent(self, req: AgentStatusRequest):
        async with self.lock:
            if req.agent_id not in self.agents or req.agent_info is None:
                return {
                    "result": False
                }
            
            self.agents[req.agent_id] = req.agent_info
            return {
                "result": True
            }

    def run(self, host: str, port: int):
        app = FastAPI()
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/agent")(self.get_agent)
        router.get("/agent/list")(self.get_agents)
        router.post("/agent/add")(self.add_agent)
        router.put("/agent/update")(self.update_agent)
        router.delete("/agent/delete")(self.delete_agent)
        app.include_router(router)
        uvicorn.run(app, host=host, port=port)

class UserRequest(BaseModel):
    user_id: str
    query: str

class RegionalWebServer:
    agent_monitor_addr: str

    def __init__(self, agent_monitor_addr: str):
        self.agent_monitor_adr = agent_monitor_addr

    async def ready(self):
        return "web server ok"
    
    async def query(self, req: UserRequest):
        return {
            "task_id": 0,
        }
    
    def run(self, host: str, port: int):
        app = FastAPI()
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.post("/query")(self.query)
        app.include_router(router)
        uvicorn.run(app, host=host, port=port)
    
class RegionalManager:
    host: str
    web_port: int
    monitor_port: int

    def __init__(self, host: str = "0.0.0.0", web_port: int = 8100, monitor_port: int = 8101):
        self.host = host
        self.web_port = web_port
        self.monitor_port = monitor_port

    def run(self):
        agent_monitor = RegionalAgentMonitor()

        def agent_monitor_worker():
            agent_monitor.run(self.host, self.monitor_port)

        agent_monitor_process = multiprocessing.Process(target=agent_monitor_worker)
        agent_monitor_process.start()
        agent_monitor_addr = f'http://{self.host}:{self.monitor_port}'

        web_server = RegionalWebServer(agent_monitor_addr)
        def web_server_worker():
            web_server.run(self.host, self.web_port)

        web_server_process = multiprocessing.Process(target=web_server_worker)
        web_server_process.start()

        try:
            agent_monitor_process.join()
            web_server_process.join()
        except KeyboardInterrupt:
            print("Stopping servers...")
            agent_monitor_process.terminate()
            web_server_process.terminate()
