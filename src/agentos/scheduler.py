import asyncio
import queue
from typing import Tuple

class QueueTask:
    def __init__(self, task_id: int, task_query: str, task_priority: int, task_exec_count: int):
        self.task_id = task_id
        self.task_query = task_query
        self.task_priority = task_priority
        self.task_exec_count = task_exec_count
        self.result = ""
        self.lock = asyncio.Lock()
        self.cond = asyncio.Condition(self.lock)

    async def set_result(self, result):
        async with self.lock:
            self.result = result
            self.cond.notify_all()

    async def wait(self):
        async with self.lock:
            await self.cond.wait()

class FIFOPolicy:
    def __init__(self, capacity: int):
        self.lock = asyncio.Lock()
        self.capacity = capacity
        self.q = queue.Queue()
        self._size = 0

    async def size(self) -> Tuple[int, int]:
        async with self.lock:
            return self._size, self.capacity
        
    async def full(self) -> bool:
        async with self.lock:
            return self._size >= self.capacity
        
    async def workload(self) -> int:
        async with self.lock:
            return int(self._size / self.capacity * 100)

    async def push(self, task: QueueTask) -> bool:
        async with self.lock:
            if self._size >= self.capacity:
                return False
            
            self.q.put(task)
            self._size += 1
            return True

    async def pop(self) -> QueueTask | None:
        async with self.lock:
            if self._size == 0:
                return None
            
            self._size -= 1
            return self.q.get()

class MLFQPolicy:
    def __init__(self, q_num: int, capacity: int):
        self.lock = asyncio.Lock()
        self.capacity = capacity
        self.q_num = q_num
        self.qlist = [queue.Queue() for _ in range(q_num)]
        self.tokens = [q_num - i for i in range(q_num)]
        self.tokens_left = sum(self.tokens)
        self._size = 0

    async def size(self) -> int:
        async with self.lock:
            return self._size

    async def push(self, task: QueueTask) -> bool:
        async with self.lock:
            if self._size >= self.capacity:
                return False
            
            task_level = min(task.task_exec_count, self.q_num-1)
            task_level = max(task_level, task.task_priority)
            self.qlist[task_level].put(task)
            
            self._size += 1
            return True

    async def pop(self) -> QueueTask | None:
        async with self.lock:
            if self._size == 0:
                return None
            
            if self.tokens_left == 0:
                self.tokens = [self.q_num - i for i in range(self.q_num)]
                self.tokens_left = sum(self.tokens)

            task = None
            for i, count in enumerate(self.tokens):
                if count > 0:
                    self.tokens[i] -= 1
                    self.tokens_left -= 1
                    if not self.qlist[i].empty():
                        task = self.qlist[i].get()
                        break
            
            self._size -= 1
            return task