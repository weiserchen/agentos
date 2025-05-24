import asyncio
from typing import List

import pytest

from agentos.scheduler import FIFOPolicy, QueueTask
from agentos.tasks.elem import TaskEvent


@pytest.mark.asyncio
async def test_fifo_policy():
    policy = FIFOPolicy(100)

    input_size = 1000
    out_tasks: List[QueueTask] = []

    async def producer():
        for i in range(input_size):
            task_event = TaskEvent(
                task_id=i,
                task_description="a task",
                task_evaluation="task {i}",
            )
            task = QueueTask(task_event)
            while True:
                success = await policy.push(task)
                if success:
                    break
                else:
                    await asyncio.sleep(0.1)
                    continue

    async def consumer():
        for i in range(input_size):
            while True:
                task = await policy.pop()
                if task is None:
                    await asyncio.sleep(0.1)
                    continue

                out_tasks.append(task)
                break

    await asyncio.gather(producer(), consumer())

    for i in range(input_size):
        assert out_tasks[i].task_event.task_id == i
