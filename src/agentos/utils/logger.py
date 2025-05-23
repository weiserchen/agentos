import asyncio
import queue
import logging
import sys
import time

class AsyncLogger:
    def __init__(self, logger_name = "default", log_file='stdio', level=logging.INFO, capacity = 1000):
        self.lock = asyncio.Lock()
        self.cond = asyncio.Condition(self.lock)
        self._size = 0
        self.capacity = capacity
        self.queue = queue.Queue()
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(level)

        handler = None
        if log_file == "stdio":
            handler = logging.StreamHandler(sys.stderr)
        else:
            handler = logging.FileHandler(log_file)

        formatter = logging.Formatter(
            '[%(name)s] - %(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S',
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def start(self):
        return asyncio.create_task(self.log_worker())

    async def log_worker(self):
        MAX_LOGS = 10
        sleep_time = 0.1
        while True:
            records = []
            async with self.lock:
                for _ in range(MAX_LOGS):
                    if self._size == 0:
                        break

                    record = self.queue.get()
                    self._size -= 1
                    if record is None:
                        return
                    records.append(record)

            if len(records) == 0:
                await asyncio.sleep(sleep_time)
            else:
                for record in records:
                    self.logger.handle(record)

    async def log(self, level, msg, *args):
        record = self.logger.makeRecord(
            self.logger.name, level, fn=None, lno=0, msg=msg, args=args, exc_info=None
        )
        async with self.lock:
            while self._size >= self.capacity:
                await self.cond.wait()

            self.queue.put(record)
            self._size += 1
            self.cond.notify_all()

    async def info(self, msg, *args):
        await self.log(logging.INFO, msg, *args)

    async def stop(self):
        async with self.lock:
            self.queue.put(None)
            self._size += 1
            self.cond.notify_all()
