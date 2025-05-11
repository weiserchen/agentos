from fastapi import APIRouter, FastAPI
from typing import Dict, List

from agentos.tasks import TaskEvent, TaskCoordinator, TaskEventType
import asyncio
import uvicorn

class Agent:
    def __init__(self):
        pass

class AgentProxy:
    coord_map: Dict[int, TaskCoordinator]
    doc_map: Dict[str, str]

    def __init__(self):
        self.agent = Agent()
        self.coord_map = dict()
        self.doc_map = dict()
        self.lock = asyncio.Lock()

    async def process_event(self, e: TaskEvent):
        match e.task_type:
            case TaskEventType.AGENT_EXEC:
                await self.call_agent(e)
            case TaskEventType.AGENT_COORD:
                await self.handle_coordinator(e)
            case _:
                pass

    async def handle_coordinator(self, e: TaskEvent) -> bool:
        coord = None
        async with self.lock:
            if e.task_id not in self.coord_map:
                return False
            coord = self.coord_map[e.task_id]
        
        coord.process_event(e)

    async def call_agent(self, e: TaskEvent):
        pass

    async def fetch_documents(self, docs: List[str]):
        for doc in docs:
            async with self.lock:
                # fetch a document and store in the doc_map
                pass

    async def checkpoint(self):
        pass

    def run(self, host="0.0.0.0", port=10000):
        app = FastAPI()
        router = APIRouter()
        router.post("/event")(self.process_event)
        app.include_router(router)
        uvicorn.run(app, host=host, port=port)





