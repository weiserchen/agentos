import asyncio
import queue
import logging
import sys
import time

class AsyncLogger:
    def __init__(self, logger_name = "default", log_file='stdio', level=logging.INFO):
        self.lock = asyncio.Lock()
        self.queue = queue.Queue()
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(level)

        handler = None
        if log_file == "stdio":
            handler = logging.StreamHandler(sys.stderr)
        else:
            handler = logging.FileHandler(log_file)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def log_worker(self):
        MAX_LOGS = 10
        sleep_time = 0.1
        while True:
            records = []
            async with self.lock:
                for _ in range(MAX_LOGS):
                    if self.queue.qsize() == 0:
                        break

                    record = self.queue.get()
                    if record is None:
                        return
                    records.append(record)

            for record in records:
                self.logger.handle(record)

            time.sleep(sleep_time)
            

    async def log(self, level, msg, *args):
        record = self.logger.makeRecord(
            self.logger.name, level, fn=None, lno=0, msg=msg, args=args, exc_info=None
        )
        async with self.lock:
            self.queue.put(record)

    async def stop(self):
        async with self.lock:
            self.queue.put(None)

# Usage in asyncio context
# async def main():
#     logger = AsyncLogger()
#     worker_task = asyncio.create_task(logger.log_worker())
#     logger.log(logging.INFO, "Hello async logging")
#     await asyncio.sleep(0.5)
#     await logger.stop()
#     await worker_task