import asyncio
import time

import aiohttp

from agentos.utils.logger import AsyncLogger

gateway_host = "127.0.0.1"
gateway_port = 10000
gateway_url = f"http://{gateway_host}:{gateway_port}"


async def main():
    try:
        logger = AsyncLogger("client")
        await logger.start()

        inputs = [
            {
                "task_name": "code_generation",
                "task_description": "MULTITHREADED BLOCKED MATRIX MULTIPLICATION IN C++",
            },
            {
                "task_name": "code_generation",
                "task_description": "MULTITHREADED BLOCKED MATRIX MULTIPLICATION IN C++",
            },
            # {
            #     "task_name": "code_generation",
            #     "task_description": "MULTITHREADED BLOCKED MATRIX MULTIPLICATION IN C++",
            # },
        ]

        async def execute_task(data):
            task_id = None
            async with aiohttp.ClientSession() as session:
                async with session.post(gateway_url + "/query", json=data) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"]
                    task_id = body["task_id"]

            sleep_interval = 10
            while True:
                async with aiohttp.ClientSession() as session:
                    data = {
                        "task_id": task_id,
                    }
                    async with session.get(
                        gateway_url + "/task/status", params=data
                    ) as response:
                        assert response.status < 300
                        body = await response.json()
                        status = body["status"]
                        if status == "not exist":
                            error_str = f"task {task_id} not exist"
                            await logger.error(f"[Task {task_id}] {error_str}")
                            raise Exception(f"task {task_id} not exist")
                        elif status == "ok":
                            assert body["success"]
                            result = body["result"]
                            assert result != ""
                            await logger.debug(f"[Task {task_id}] result: \n{result}")
                            break
                        else:
                            await logger.warning(
                                f"[Task {task_id}] waiting for result..."
                            )
                            await asyncio.sleep(sleep_interval)

        start_time = time.perf_counter()
        futures = []
        for input in inputs:
            futures.append(execute_task(input))

        await asyncio.gather(*futures)
        end_time = time.perf_counter()

        total_time = end_time - start_time
        await logger.info(f"Total time: {total_time:.6f} seconds")

    finally:
        await logger.stop()


if __name__ == "__main__":
    asyncio.run(main())
