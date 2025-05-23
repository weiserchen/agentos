import pytest
import asyncio
from agentos.tasks.elem import TaskEvent, TaskEventType
from agentos.scheduler import QueueTask, FIFOPolicy
from agentos.utils.logger import AsyncLogger
from typing import List

@pytest.mark.asyncio
async def test_async_logger():
    policy = FIFOPolicy(10)

    input_size = 100
    out_tasks: List[QueueTask] = []
    producer_logger = AsyncLogger("producer")
    consumer_logger = AsyncLogger("consumer")

    producer_log_worker = await producer_logger.start()
    consumer_log_worker = await consumer_logger.start()

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
                    await producer_logger.info(f"enqueue task {i+1}")
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
                await consumer_logger.info(f"dequeue task {i+1}")
                break
                
    await asyncio.gather(producer(), consumer())
    await asyncio.gather(producer_logger.stop(), consumer_logger.stop())

    for i in range(input_size):
        assert out_tasks[i].task_event.task_id == i

    # await asyncio.gather(producer_log_worker, consumer_log_worker)