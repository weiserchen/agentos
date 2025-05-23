from typing import List, Any
from enum import Enum
from pydantic import BaseModel

class TaskEventType(Enum):
    AGENT_EXEC = 1
    AGENT_DONE = 2
    AGENT_COORD = 3
    AGENT_HANDOFF = 4

class TaskEvent(BaseModel):
    task_id: int
    task_description: str
    task_evaluation: str

class AgentCallTaskEvent(BaseModel):
    task_description: str
    task_stop: Any

class CoordinatorTaskEvent(BaseModel):
    task_name: str
    task_description: str

class TaskNode:
    description: str
    evaluation: str
    n_rounds: int
    n_samples: int
    n_voters: int

    def __init__(self, description: str, evaluation: str, n_rounds: int, n_samples: int, n_voters: int):
        self.description = description
        self.evaluation = evaluation
        self.n_rounds = n_rounds
        self.n_samples = n_samples
        self.n_voters = n_voters