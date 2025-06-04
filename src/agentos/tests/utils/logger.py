import asyncio
import logging
from typing import List

import pytest

from agentos.scheduler import FIFOPolicy, QueueTask
from agentos.tasks.elem import TaskEvent
from agentos.utils.logger import AsyncLogger
from agentos.utils.sleep import random_sleep


@pytest.mark.asyncio
async def test_async_logger():
    policy = FIFOPolicy(10)

    input_size = 100
    out_tasks: List[QueueTask] = []
    producer_logger = AsyncLogger("producer", level=logging.DEBUG)
    consumer_logger = AsyncLogger("consumer", level=logging.DEBUG)

    await producer_logger.start()
    await consumer_logger.start()

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
                    await producer_logger.info(f"enqueue task {i + 1}")
                    break
                else:
                    await random_sleep(0.1)
                    continue

    async def consumer():
        for i in range(input_size):
            while True:
                task = await policy.pop()
                if task is None:
                    await random_sleep(0.1)
                    continue

                out_tasks.append(task)
                await consumer_logger.info(f"dequeue task {i + 1}")
                break

    await asyncio.gather(producer(), consumer())
    await asyncio.gather(producer_logger.stop(), consumer_logger.stop())

    for i in range(input_size):
        assert out_tasks[i].task_event.task_id == i
