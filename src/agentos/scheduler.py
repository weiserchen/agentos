import asyncio
import queue

class QueueTask:
    def __init__(self, task_id: int, task_query: str, task_priority: int, task_exec_count: int):
        self.task_id = task_id
        self.task_query = task_query
        self.task_priority = task_priority
        self.task_exec_count = task_exec_count

class FIFOPolicy:
    def __init__(self, capacity: int):
        self.lock = asyncio.Lock()
        self.capacity = capacity
        self.q = queue.Queue()

    async def push(self, task: QueueTask) -> bool:
        async with self.lock:
            if len(self.q) >= self.capacity:
                return False
            
            self.q.put(task)
            return True

    async def pop(self) -> QueueTask | None:
        async with self.lock:
            if self.q.empty():
                return None
            
            return self.q.get()

class MLFQPolicy:
    def __init__(self, q_num: int, capacity: int):
        self.lock = asyncio.Lock()
        self.capacity = capacity
        self.q_num = q_num
        self.qlist = [queue.Queue() for _ in range(q_num)]
        self.tokens = [q_num - i for i in range(q_num)]
        self.tokens_left = sum(self.tokens)
        self.size = 0

    async def push(self, task: QueueTask) -> bool:
        async with self.lock:
            if self.size >= self.capacity:
                return False
            
            task_level = min(task.task_exec_count, self.q_num-1)
            task_level = max(task_level, task.task_priority)
            self.qlist[task_level].put(task)
            
            self.size += 1
            return True

    async def pop(self) -> QueueTask | None:
        async with self.lock:
            if self.size == 0:
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
            
            self.size -= 1
            return task