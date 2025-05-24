
import aiohttp
import asyncio
import time
import random
from typing import List, Tuple


async def _send_req_worker(base_url: str, req: dict, latency_list: List[float], response_list: List[dict], index: int):
    async with aiohttp.ClientSession() as session:
        start_time = time.time()

        try:
            # Submit the request and get a task_id
            async with session.post(f"{base_url}/tasks", json=req) as response: # task is an example idk what is your endpoint's name
                res_json = await response.json()
                task_id = res_json.get("task_id")
                if not task_id:
                    latency_list[index] = -1
                    response_list[index] = {"error": "No task_id"}
                    return

            # Poll for status
            status_url = f"{base_url}/tasks/{task_id}" # task is an example idk what is your endpoint's name
            while True:
                await asyncio.sleep(3)
                async with session.get(status_url) as status_resp:
                    status_json = await status_resp.json()
                    if status_json.get("status") == "completed":
                        break

            latency = time.time() - start_time
            latency_list[index] = latency
            response_list[index] = status_json.get("result", {})

        except Exception as e:
            latency_list[index] = -1
            response_list[index] = {"error": str(e)}


def send_req(base_url: str, req: dict, latency_list: List[float], response_list: List[dict], index: int):
    return asyncio.create_task(_send_req_worker(base_url, req, latency_list, response_list, index))


async def send_all(base_url: str, req_list: List[dict]):
    latencies = [0.0] * len(req_list)
    responses = [{} for _ in range(len(req_list))]
    tasks = [send_req(base_url, req, latencies, responses, i) for i, req in enumerate(req_list)]
    await asyncio.gather(*tasks)
    return responses, latencies


async def send_in_interval(base_url: str, req_list: List[dict], interval_range: Tuple[int, int]):
    latencies = [0.0] * len(req_list)
    responses = [{} for _ in range(len(req_list))]
    tasks = []

    for i, req in enumerate(req_list):
        if i > 0:
            await asyncio.sleep(random.uniform(*interval_range))
        task = send_req(base_url, req, latencies, responses, i)
        tasks.append(task)

    await asyncio.gather(*tasks)
    return responses, latencies


def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


async def send_batch_interval(base_url: str, req_list: List[dict], interval_range: Tuple[int, int], batch_size: int):
    latencies = [0.0] * len(req_list)
    responses = [{} for _ in range(len(req_list))]

    for batch_idx, batch in enumerate(chunk_list(list(enumerate(req_list)), batch_size)):
        if batch_idx > 0:
            await asyncio.sleep(random.uniform(*interval_range))
        tasks = [send_req(base_url, req, latencies, responses, i) for i, req in batch]
        await asyncio.gather(*tasks)

    return responses, latencies


async def send_dynamic_batch_interval(base_url: str, req_list: List[dict], interval_range: Tuple[int, int], batch_range: Tuple[int, int]):
    latencies = [0.0] * len(req_list)
    responses = [{} for _ in range(len(req_list))]
    i = 0
    batch_idx = 0

    while i < len(req_list):
        if batch_idx > 0:
            await asyncio.sleep(random.uniform(*interval_range))
        batch_size = random.randint(*batch_range)
        batch = [(i + j, req_list[i + j]) for j in range(min(batch_size, len(req_list) - i))]
        tasks = [send_req(base_url, req, latencies, responses, idx) for idx, req in batch]
        await asyncio.gather(*tasks)
        i += len(batch)
        batch_idx += 1

    return responses, latencies


if __name__ == "__main__":
    async def main():
        base_url = "http://localhost:8100"
        dummy_request = {
            "user_id": 1,
            "task_type": "sample",
            "global_epoch": 1,
            "regional_epoch": 1,
            "task_description": "test run"
        }

        req_list = [dummy_request for _ in range(100)]

        print("Sending 100 requests concurrently...")
        responses, latencies = await send_all(base_url, req_list)

        for i, (resp, lat) in enumerate(zip(responses, latencies)):
            print(f"Request #{i + 1}: latency = {lat:.2f}s | response = {resp}")

    asyncio.run(main())
