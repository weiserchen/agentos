from fastapi import APIRouter, FastAPI
import uvicorn

class RegionalWebServer:
    def __init__(self):
        self.router = APIRouter()
        self.router.get("/ready/")(self.ready)

    async def ready(self):
        return "ok"
    

class RegionalAgentMonitor:
    def __init__(self):
        pass

class RegionalManager:
    def __init__(self):
        self.app = FastAPI()
        self.web_server = RegionalWebServer()
        self.agent_monitor = RegionalAgentMonitor()

    def run(self, host="127.0.0.1", port=8000):
        self.app.include_router(self.web_server.router)
        uvicorn.run(self.app, host=host, port=port)
