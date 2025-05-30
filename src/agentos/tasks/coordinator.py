from typing import Awaitable, Callable, Dict

from agentos.tasks.elem import TaskNode
from agentos.tasks.executor import AgentInfo, SimpleTreeTaskExecutor
from agentos.utils.logger import AsyncLogger


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
