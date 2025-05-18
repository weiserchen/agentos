import pytest
import asyncio
from agentos.scheduler import QueueTask, FIFOPolicy
from typing import List

@pytest.mark.asyncio
async def test_queue_task_wait():
    task = QueueTask(1, "test task wait", 1, 1)

    async def producer():
        await task.wait()

    async def consumer():
        await asyncio.sleep(0.5)
        await task.set_result("ok")

    await asyncio.gather(producer(), consumer())

    assert task.result == "ok"

@pytest.mark.asyncio
async def test_fifo_policy():
    policy = FIFOPolicy(100)

    input_size = 1000
    out_tasks: List[QueueTask] = []

    async def producer():
        for i in range(input_size):
            task = QueueTask(i, f"task {i}", 0, 0)
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
        assert out_tasks[i].task_id == i