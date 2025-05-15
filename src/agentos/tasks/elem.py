from typing import List
from enum import Enum
from pydantic import BaseModel

class TaskEventType(Enum):
    AGENT_EXEC = 1
    AGENT_DONE = 2
    AGENT_COORD = 3
    AGENT_HANDOFF = 4

class TaskEvent(BaseModel):
    sender: str
    receiver: str
    task_type: TaskEventType
    task_id: int
    task_node: str
    task_priority: int
    task_history: List[str]
    task_exec_count: int
    task_msg: str

class TaskNode:
    name: str
    children: List[str]
    agent: str
    description: str

    def __init__(self, name: str, description: str, agent: str, children: List[str]):
        self.name = name
        self.description = description
        self.target_agent = agent
        self.children = children