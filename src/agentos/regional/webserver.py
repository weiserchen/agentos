from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
import uvicorn


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