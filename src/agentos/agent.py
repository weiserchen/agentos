from fastapi import APIRouter, FastAPI
from typing import Dict, List, Tuple
from tasks.elem import TaskEvent, TaskEventType
from scheduler import FIFOPolicy, QueueTask
from tasks.graph import TaskGraphCoordinator
import asyncio
import uvicorn
import threading
import time
import aiohttp
import json

class Agent:
    def __init__(self):
        pass

class AgentProxy:
    agents_list: List[Tuple[str, int]]
    coord_map: Dict[int, TaskGraphCoordinator]
    doc_map: Dict[str, str]

    def __init__(self, monitor_url: str):
        self.agent = Agent()
        self.coord_map = dict()
        self.agents_list = []
        self.doc_map = dict()
        self.monitor_url = monitor_url
        self.policy = FIFOPolicy(100)
        self.lock = asyncio.Lock()

        async def invoke_agent() -> str:
            return ""

        async def execute_task():
            while True:
                task = await self.policy.pop()
                if task is None:
                    await asyncio.sleep(0.1)
                    continue
                
                res = await invoke_agent()
                task.set_result(res)

        async def update_membership():
            while True:
                async with aiohttp.ClientSession() as session:
                    async with session.get(monitor_url) as response:
                        if response.status < 300:
                            body = await response.text()
                            json_body = json.loads(body)
                            
                            agent_set = []
                            for member in json_body['members']:
                                agent_set.append((member['url'], member['workload']))

                            sorted(agent_set, key=lambda x: x[1], reverse=True)
                            async with self.lock:
                                self.agents_list = agent_set

                time.sleep(5)

        self.membership_task = update_membership
        self.executor_task = execute_task

    async def run(self, host: str, port: int):
        app = FastAPI()
        router = APIRouter()
        router.post("/coordinator")(self.handle_coordinator)
        router.post("/call")(self.call_agent)
        app.include_router(router)
        asyncio.create_task(self.membership_task)
        asyncio.create_task(self.executor_task)
        uvicorn.run(app, host=host, port=port)

    async def get_status(self):
        return {
            "workload": self.policy.workload(),
        }

    async def handle_coordinator(self, e: TaskEvent) -> bool:
        coord = None
        async with self.lock:
            if e.task_id not in self.coord_map:
                self.coord_map[e.task_id] = TaskGraphCoordinator("")
            coord = self.coord_map[e.task_id]
        
        coord.process_event(e)

    async def call_agent(self, e: TaskEvent):
        task = QueueTask(e.task_id, e.task_msg, e.task_priority, e.task_exec_count)
        self.policy.push(task)
        await task.wait()
        return {
            "result": task.result
        }

    async def fetch_documents(self, docs: List[str]):
        for doc in docs:
            async with self.lock:
                # fetch a document and store in the doc_map
                pass

    async def checkpoint(self):
        pass

    async def get_other_agents(self) -> List[str]:
        async with self.lock:
            return self.agents_list

    def run(self, host="0.0.0.0", port=10000):
        app = FastAPI()
        router = APIRouter()
        router.post("/event")(self.process_event)
        app.include_router(router)
        uvicorn.run(app, host=host, port=port)





