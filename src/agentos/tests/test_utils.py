import pytest
import asyncio
from agentos.scheduler import QueueTask, FIFOPolicy
from agentos.utils import AsyncLogger
from typing import List

@pytest.mark.asyncio
async def test_fifo_policy():
    policy = FIFOPolicy(10)

    input_size = 100
    out_tasks: List[QueueTask] = []
    producer_logger = AsyncLogger("producer")
    consumer_logger = AsyncLogger("consumer")

    producer_log_worker = producer_logger.start()
    consumer_log_worker = consumer_logger.start()

    async def producer():
        for i in range(input_size):
            task = QueueTask(i, f"task {i}", 0, 0)
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

    await producer_logger.stop()
    await consumer_logger.stop()

    for i in range(input_size):
        assert out_tasks[i].task_id == i

    await asyncio.gather(producer_log_worker, consumer_log_worker)