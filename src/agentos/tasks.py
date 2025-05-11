from pydantic import BaseModel
from typing import Dict, List, Set, Any
from enum import Enum
import asyncio
import json

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

def parse_task_graph(graph: Dict[str, Any]) -> Dict[str, TaskNode]:
    node_map = dict()
    def parse_rec(parent_name: str, graph: Dict[str, Any]):
        if parent_name == "":
            node_name = "root"
            node_agent = ""
            node_desc = graph['description']
        else:
            node_name = "-".join(parent_name, graph['name'])
            node_agent = graph['agent']
            node_desc = graph['description']
        
        node_children = []
        for key, value in graph.items():
            if key != 'name' and key != 'description':
                child_name = parse_rec(node_name, value)
                node_children.append(child_name)

        node = TaskNode(node_name, node_desc, node_agent, node_children)
        node_map[node_name] = node
        return node_name

    parse_rec("", graph)
    return node_map

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

class TaskCoordinator:
    task_graph: Dict[str, TaskNode]
    frontier: Set[str]

    def __init__(self, graph: str):
        self.lock = asyncio.Lock()
        self.frontier = set()
        graph_json = json.loads(graph)
        self.task_graph = parse_task_graph(graph_json)

    async def task_start(self):
        root_node = self.task_graph['root']
        for child in root_node.children:
            async with self.lock:
                self.frontier.add(child)
            # TODO: send query to agent

    # result: True: coordinator completed
    async def process_event(self, e: TaskEvent) -> bool:
        if e.task_type == TaskEventType.AGENT_DONE:
            node = self.task_graph[e.task_node]
            async with self.lock:
                self.frontier.remove(e.task_node)
                for child in node.children:
                    self.frontier.add(child)

                if len(self.frontier) == 0:
                    return True
            
            for child in node.children:
                async with self.lock:
                    # TODO: sent request to agent
                    pass

        return False
                    
            