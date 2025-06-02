import asyncio
import random
import statistics
import time
import logging
from typing import List

import aiohttp

from agentos.utils.logger import AsyncLogger
from .benchmark_tasks import benchmark_tasks
from agentos.tasks.utils import http_post, http_get 

random.seed(42)

REQ_RATE = 0.2
RUN_TIME_SEC = 30
POLL_INTERVAL = 1

gateway_host = "127.0.0.1"
gateway_port = 10000
gateway_url = f"http://{gateway_host}:{gateway_port}"

latencies: List[float] = []
completed = 0
stats_lock = asyncio.Lock()


async def execute_task(logger: AsyncLogger) -> None:
    """
    One end-to-end task: POST /query → poll /task/status → collect result.
    """
    global completed

    t_start = time.perf_counter()

    REQUEST_BODY = benchmark_tasks[random.randint(0, len(benchmark_tasks) - 1)]
    resp = await http_post(f"{gateway_url}/query", REQUEST_BODY)
    assert resp["success"], f"Failed to submit task: {resp['result']}"
    task_id = resp["body"]["task_id"]

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        resp = await http_get(f"{gateway_url}/task/status", params = {"task_id": task_id})
        assert resp["success"]
        body = resp["body"]

        if body["status"] == "ok":
            if body["success"] is False:
                await logger.error(f"[Task {task_id}] - failed with error: {body['result']}")
                return
            break
        elif body["status"] == "not exist":
            await logger.error(f"[Task {task_id}] - not found")
            return

    latency = time.perf_counter() - t_start

    async with stats_lock:
        latencies.append(latency)
        completed += 1
        elapsed = time.perf_counter() - START_TIME
        avg_lat = statistics.fmean(latencies)
        throughput = completed / elapsed if elapsed > 0 else 0.0
        await logger.info(
            f"[{completed:5d} done]  "
            f"avg-latency = {avg_lat:7.3f}s  "
            f"throughput = {throughput:6.2f} req/s"
        )


async def poisson_arrival(logger: AsyncLogger) -> None:
    while True:
        now = time.perf_counter()
        if now - START_TIME >= RUN_TIME_SEC:
            break

        inter_arrival = random.expovariate(REQ_RATE)  # exponential distribution
        await asyncio.sleep(inter_arrival)

        asyncio.create_task(execute_task(logger))


async def main() -> None:
    global START_TIME
    logger = AsyncLogger("benchmark", level=logging.INFO)
    await logger.start()

    try:
        START_TIME = time.perf_counter()
        await poisson_arrival(logger)
        await logger.info("Stopped dispatcing new requests. Waiting for in-flight requests ...")

        while True:
            async with stats_lock:
                in_flight = len(
                    [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                ) - 1  # subtract this main() task
                if in_flight == 0:
                    break
            await asyncio.sleep(1)

        await logger.info(
            "Finished.\n"
            f"Total completed: {completed}\n"
            f"Average latency: {statistics.fmean(latencies):.3f}s\n"
            f"Overall throughput: {completed / (time.perf_counter() - START_TIME):.2f} req/s"
        )

    finally:
        await logger.stop()


if __name__ == "__main__":
    asyncio.run(main())