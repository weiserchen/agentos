import asyncio
import logging
import queue
import sys

from agentos.utils.sleep import random_sleep


class LogColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    COLORS = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[95m",  # Magenta
    }

    NAME_COLOR = "\033[96m"  # Cyan for logger name


class ColorFormatter(logging.Formatter):
    def format(self, record):
        # Colorize level name
        level_color = LogColors.COLORS.get(record.levelname, LogColors.RESET)
        record.levelname = f"{level_color}{record.levelname}{LogColors.RESET}"

        # Colorize logger name
        record.name = f"{LogColors.NAME_COLOR}{record.name}{LogColors.RESET}"

        return super().format(record)


class AsyncLogger:
    def __init__(
        self,
        logger_name="default",
        log_file="console",
        level=logging.INFO,
        capacity=1000,
    ):
        self.lock = asyncio.Lock()
        self.cond = asyncio.Condition(self.lock)
        self.stop_lock = asyncio.Lock()
        self.stop_cond = asyncio.Condition(self.stop_lock)
        self.stopped = False
        self._size = 0
        self.capacity = capacity
        self.queue = queue.Queue()
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(level)

        handler = None
        formatter = None
        if log_file == "console":
            formatter = ColorFormatter(
                "[%(name)s] - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
            )
            handler = logging.StreamHandler(sys.stderr)
        else:
            formatter = logging.Formatter(
                "[%(name)s] - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
            )
            handler = logging.FileHandler(log_file)

        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def start(self):
        return asyncio.create_task(self.log_worker())

    async def log_worker(self):
        MAX_LOGS = 10
        sleep_time = 0.5
        shutdown = False
        while not shutdown:
            records = []
            async with self.lock:
                for _ in range(MAX_LOGS):
                    if self._size == 0:
                        break

                    record = self.queue.get()
                    self._size -= 1
                    if record is None:
                        shutdown = True
                        break
                    records.append(record)
                self.cond.notify_all()

            if len(records) == 0:
                await random_sleep(sleep_time)
            else:
                for record in records:
                    self.logger.handle(record)

        async with self.stop_lock:
            self.stopped = True
            self.stop_cond.notify_all()

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

    async def debug(self, msg, *args):
        await self.log(logging.DEBUG, msg, *args)

    async def warning(self, msg, *args):
        await self.log(logging.WARNING, msg, *args)

    async def error(self, msg, *args):
        await self.log(logging.ERROR, msg, *args)

    async def stop(self):
        await self.log(logging.INFO, "stopping logger...")

        async with self.lock:
            self.queue.put(None)
            self._size += 1
            self.cond.notify_all()

        # wait for the logger to flush all the log
        async with self.stop_lock:
            while not self.stopped:
                await self.stop_cond.wait()
