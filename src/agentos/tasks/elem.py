from enum import Enum
from typing import Any

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


class TaskAction(str, Enum):
    GENERATION = "generation"
    VOTING = "voting"
    DEFAULT = ""


class AgentCallTaskEvent(BaseModel):
    task_id: int
    task_round: int
    task_action: TaskAction
    task_description: str
    task_stop: Any


class CoordinatorTaskEvent(BaseModel):
    task_id: int
    task_name: str
    task_description: str


class TaskQueryEvent(BaseModel):
    task_name: str
    task_description: str


class TaskCompleteEvent(BaseModel):
    task_id: int
    success: bool
    result: str


class TaskNode:
    description: str
    evaluation: str
    n_rounds: int
    n_samples: int
    n_voters: int

    def __init__(
        self,
        description: str,
        evaluation: str,
        n_rounds: int,
        n_samples: int,
        n_voters: int,
    ):
        self.description = description
        self.evaluation = evaluation
        self.n_rounds = n_rounds
        self.n_samples = n_samples
        self.n_voters = n_voters

    def __str__(self):
        return f"\ndescription: {self.description}\nevaluation: {self.evaluation}\nn_rounds: {self.n_rounds}\nn_samples: {self.n_samples}\nn_voters: {self.n_voters}"
