from typing import Awaitable, Callable, Dict

from agentos.tasks.elem import TaskNode
from agentos.tasks.executor import AgentInfo, SimpleTreeTaskExecutor
from agentos.utils.logger import AsyncLogger


class SingleNodeCoordinator:
    def __init__(
        self,
        task_id: int,
        term: int,
        task_node: TaskNode,
        get_agents: Callable[[], Awaitable[Dict[str, AgentInfo]]],
    ):
        self.task_id = task_id
        self.term = term
        self.round = 0
        self.task_node = task_node
        self.get_agents = get_agents
        self.logger = AsyncLogger(f"task-{task_id}-coordinator")
        self.result = None
        self.success = False
        self.completed = False

    async def run(self):
        try:
            await self.logger.start()
            executor = SimpleTreeTaskExecutor(
                self.logger,
                self.task_id,
                self.task_node,
                self.get_agents,
            )
            async for _ in executor.run():
                self.success = not executor.failed
                self.round = executor.round
                self.result = executor.result
                self.completed = executor.completed
                yield

        except Exception as e:
            self.success = False
            self.completed = True
            err_str = f"coordinator - exception: {e}"
            await self.logger.error(err_str)
            self.result = err_str
        finally:
            await self.logger.stop()
