from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from typing import List, Dict
import multiprocessing
import asyncio
import uvicorn

class AgentInfo(BaseModel):
    id: str
    addr: str
    workload: int
    queue_size: int


class RegionalAgentMonitor:
    agents: Dict[str, AgentInfo]

    def __init__(self):
        self.agents = dict()
        self.lock = asyncio.Lock()
        self.router = APIRouter()
        self.router.get("/ready")(self.ready)

    async def ready(self):
        return {
            "status": "agent monitor ok"
        }

    async def get_agents(self) -> List[str]:
        async with self.lock:
            return {
                "agents": list(self.agents.keys())
            }
    
    async def get_agent(self, agent_id: str) -> AgentInfo | None:
        async with self.lock:
            return {
                "agent_info": self.agents.get(agent_id)
            }
    
    async def add_agent(self, agent_id: str, agent_info: AgentInfo) -> bool:
        async with self.lock:
            if agent_id in self.agents:
                return {
                    "result": False
                }
            
            self.agents[agent_id] = agent_info
            return {
                "result": True
            }
    
    async def delete_agent(self, agent_id: str) -> bool:
        async with self.lock:
            if agent_id not in self.agents:
                return {
                    "result": False
                }
            
            del self.agents[agent_id]
            return {
                "result": True
            }
        
    async def update_agent(self):
        pass

class UserRequest(BaseModel):
    user_id: str
    query: str

class RegionalWebServer:
    agent_monitor_addr: str

    def __init__(self, agent_monitor_addr: str):
        self.agent_monitor_adr = agent_monitor_addr
        self.router = APIRouter()
        self.router.get("/ready")(self.ready)
        self.router.post("/query")(self.query)

    async def ready(self):
        return "web server ok"
    
    async def query(self, req: UserRequest):
        return {
            "task_id": 0,
        }
    
class RegionalManager:
    host: str
    web_port: int
    monitor_port: int

    def __init__(self, host: str = "127.0.0.1", web_port: int = 8100, monitor_port: int = 8101):
        self.host = host
        self.web_port = web_port
        self.monitor_port = monitor_port

    def run(self):
        agent_monitor = RegionalAgentMonitor()

        def agent_monitor_worker():
            app = FastAPI()
            app.include_router(agent_monitor.router)
            uvicorn.run(app, host=self.host, port=self.monitor_port)

        agent_monitor_process = multiprocessing.Process(target=agent_monitor_worker)
        agent_monitor_process.start()
        agent_monitor_addr = f'http://{self.host}:{self.monitor_port}'

        def web_server_worker():
            app = FastAPI()
            web_server = RegionalWebServer(agent_monitor_addr)
            app.include_router(web_server.router)
            uvicorn.run(app, host=self.host, port=self.web_port)

        web_server_process = multiprocessing.Process(target=web_server_worker)
        web_server_process.start()

        try:
            agent_monitor_process.join()
            web_server_process.join()
        except KeyboardInterrupt:
            print("Stopping servers...")
            agent_monitor_process.terminate()
            web_server_process.terminate()
