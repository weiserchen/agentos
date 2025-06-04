from typing import Awaitable, Callable, Dict

from agentos.tasks.elem import TaskNode
from agentos.tasks.executor import AgentInfo, SimpleTreeTaskExecutor
from agentos.utils.logger import AsyncLogger


class SingleNodeCoordinator:
    def __init__(
        self,
        task_id: int,
        round: int,
        term: int,
        result: str,
        task_node: TaskNode,
        get_agents: Callable[[], Awaitable[Dict[str, AgentInfo]]],
        load_balancing: str = "random",
        voting_strategy: str = "naive",
    ):
        self.task_id = task_id
        self.round = round
        # used by proxy
        self.term = term
        self.result = result
        self.task_node = task_node
        self.get_agents = get_agents
        self.logger = AsyncLogger(f"task-{task_id}-coordinator")
        self.success = False
        self.completed = False
        self.load_balancing = load_balancing
        self.voting_strategy = voting_strategy

    async def run(self):
        try:
            await self.logger.start()
            executor = SimpleTreeTaskExecutor(
                self.logger,
                self.task_id,
                self.round,
                self.result,
                self.task_node,
                self.get_agents,
                self.load_balancing,
                self.voting_strategy,
            )
            async for _ in executor.run():
                if executor.round == self.task_node.n_rounds - 1:
                    self.success = not executor.failed
                else:
                    self.success = False

                self.round = executor.round
                self.result = executor.result
                self.completed = executor.completed
                yield

        except Exception as e:
            self.success = False
            self.completed = True
            err_str = f"executor - exception: {e}"
            await self.logger.error(err_str)
            self.result = err_str
        finally:
            await self.logger.stop()
