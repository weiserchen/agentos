from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
import uvicorn

class Agent:
    def __init__(self):
        pass

class AgentProxy:
    def __init__(self):
        self.app = FastAPI()
        self.agent = Agent()
    
    def run(self, host="127.0.0.1", port=10001):
        pass

class TaskEvent(BaseModel):
    sender: str
    receiver: str
    task_type: str
    task_node: str
    task_msg: str

class TaskCoordinator:
    def __init__(self):
        pass

    def process_event(self, task_event: TaskEvent) -> TaskEvent:
        pass



