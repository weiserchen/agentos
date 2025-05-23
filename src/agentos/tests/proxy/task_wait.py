import pytest
import asyncio
from agentos.tasks.elem import TaskEvent, TaskEventType
from agentos.scheduler import QueueTask, FIFOPolicy
from typing import List

@pytest.mark.asyncio
async def test_queue_task_wait():
    task_event = TaskEvent(
        task_id=1,
        task_description="a task",
        task_evaluation="test task wait",
    )
    task = QueueTask(task_event)

    async def producer():
        await task.wait()

    async def consumer():
        await asyncio.sleep(0.5)
        await task.set_result("ok")

    await asyncio.gather(producer(), consumer())

    assert task.result == "ok"