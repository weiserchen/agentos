import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, Set

from agentos.tasks.elem import TaskEvent, TaskEventType, TaskNode
from agentos.tasks.executor import AgentInfo, SimpleTreeTaskExecutor
from agentos.utils.logger import AsyncLogger


def parse_task_graph(graph: Dict[str, Any]) -> Dict[str, TaskNode]:
    node_map = dict()

    def parse_rec(parent_name: str, graph: Dict[str, Any]):
        if parent_name == "":
            node_name = "root"
            node_agent = ""
            node_desc = graph["description"]
        else:
            node_name = "-".join(parent_name, graph["name"])
            node_agent = graph["agent"]
            node_desc = graph["description"]

        node_children = []
        for key, value in graph.items():
            if key != "name" and key != "description":
                child_name = parse_rec(node_name, value)
                node_children.append(child_name)

        node = TaskNode(node_name, node_desc, node_agent, node_children)
        node_map[node_name] = node
        return node_name

    parse_rec("", graph)
    return node_map


class SingleNodeCoordinator:
    def __init__(
        self,
        task_id: int,
        task_node: TaskNode,
        get_agents: Callable[[], Awaitable[Dict[str, AgentInfo]]],
    ):
        self.task_id = task_id
        self.task_node = task_node
        self.get_agents = get_agents
        self.logger = AsyncLogger(f"task-{task_id}-coordinator")
        self.result = None
        self.success = False

    async def start(self):
        try:
            await self.logger.start()
            executor = SimpleTreeTaskExecutor(
                self.logger,
                self.task_id,
                self.task_node,
                self.get_agents,
            )
            await executor.start()
            self.success = not executor.failed
            self.result = executor.result
        except Exception as e:
            self.success = False
            self.result = f"exception: {e}"
        finally:
            await self.logger.stop()


class TaskGraphCoordinator:
    task_graph: Dict[str, TaskNode]
    frontier: Set[str]

    def __init__(self, graph: str):
        self.lock = asyncio.Lock()
        self.frontier = set()
        graph_json = json.loads(graph)
        self.task_graph = parse_task_graph(graph_json)

    async def task_start(self):
        root_node = self.task_graph["root"]
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
