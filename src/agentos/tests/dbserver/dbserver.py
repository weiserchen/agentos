import multiprocessing as mp
import os

import aiohttp
import pytest

from agentos.service.dbserver import AgentDatabaseServer
from agentos.tasks.elem import TaskStatus
from agentos.utils.logger import AsyncLogger
from agentos.utils.ready import is_url_ready

db_file = "pytest.db"
dbserver = AgentDatabaseServer(db_file)
dbserver_host = "127.0.0.1"
dbserver_port = 10003
dbserver_url = f"http://{dbserver_host}:{dbserver_port}"


def run_dbserver():
    dbserver.run(dbserver_host, dbserver_port)


@pytest.mark.asyncio
async def test_agent_dbserver():
    try:
        logger = AsyncLogger("pytest")
        await logger.start()

        dbserver_process = mp.Process(target=run_dbserver)
        dbserver_process.start()

        assert await is_url_ready(logger, dbserver_url)

        async with aiohttp.ClientSession() as session:
            task_num = 10
            test_agent = "pytest"
            curr_term = 0
            tasks = []
            for i in range(task_num):
                task = {
                    "task_agent": test_agent,
                    "task_name": f"db_task_{i}",
                    "task_description": f"db_description_{i}",
                }
                task_id = None
                async with session.post(dbserver_url + "/task", json=task) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"], body["err"]
                    task_id = body["task_id"]
                    assert task_id is not None

                task["task_id"] = task_id
                tasks.append(task)

            data = {
                "task_id": 10000,
            }
            async with session.get(dbserver_url + "/task", params=data) as response:
                assert response.status < 300
                body = await response.json()
                assert not body["success"]
                assert body["err"] is not None

            for i in range(task_num):
                task = tasks[i]
                data = {
                    "task_id": task["task_id"],
                }
                async with session.get(dbserver_url + "/task", params=data) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"], body["err"]

                    assert body["term"] == curr_term
                    assert body["task_agent"] == task["task_agent"]
                    assert body["task_status"] == TaskStatus.PENDING
                    assert body["task_name"] == task["task_name"]
                    assert body["task_description"] == task["task_description"]
                    assert body["task_result"] == ""

            data = {
                "task_agent": "non-exist agent",
            }
            async with session.get(
                dbserver_url + "/tasks/agent", params=data
            ) as response:
                assert response.status < 300
                body = await response.json()
                assert body["success"]
                assert len(body["tasks"]) == 0

            data = {
                "task_agent": test_agent,
            }
            async with session.get(
                dbserver_url + "/tasks/agent", params=data
            ) as response:
                assert response.status < 300
                body = await response.json()
                assert body["success"], body["err"]

                db_tasks = body["tasks"]
                assert len(db_tasks) == len(tasks)
                for i in range(task_num):
                    task = tasks[i]
                    db_task = db_tasks[i]

                    assert db_task["task_id"] == task["task_id"]
                    assert db_task["term"] == curr_term
                    assert db_task["task_agent"] == task["task_agent"]
                    assert db_task["task_status"] == TaskStatus.PENDING
                    assert db_task["task_name"] == task["task_name"]
                    assert db_task["task_description"] == task["task_description"]
                    assert db_task["task_result"] == ""

            curr_round = 0
            # update task progress (round 0)
            for i in range(task_num):
                task = tasks[i]
                task["task_result"] = f"task {i} round {curr_round} completed"
                data = {
                    "task_id": task["task_id"],
                    "round": curr_round,
                    "term": curr_term,
                    "result": task["task_result"],
                }
                async with session.post(
                    dbserver_url + "/task/progress", json=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"]

            # update term
            prev_term = 0
            curr_term = 1

            # (failed) update task progress
            for i in range(task_num):
                task = tasks[i]
                data = {
                    "task_id": task["task_id"],
                    "round": curr_round,
                    "term": prev_term,
                    "result": task["task_result"],
                }
                async with session.post(
                    dbserver_url + "/task/progress", json=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert not body["success"]
                    assert body["err"] is not None

            curr_round = 1
            # update task progress (round 1)
            for i in range(task_num):
                task = tasks[i]
                task["task_result"] = f"task {i} round {curr_round} completed"
                data = {
                    "task_id": task["task_id"],
                    "round": curr_round,
                    "term": curr_term,
                    "result": task["task_result"],
                }
                async with session.post(
                    dbserver_url + "/task/progress", json=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"]

            # check progress list
            for i in range(task_num):
                data = {
                    "task_id": task["task_id"],
                }
                async with session.get(
                    dbserver_url + "/task/progress/list", params=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"]

                    progress_list = body["progress_list"]
                    prev_round = -1
                    for progress in progress_list:
                        # unique and ascending
                        assert progress["round"] > prev_round
                        assert progress["term"] is not None
                        assert progress["result"] is not None

            # (successful) mark all task as completed
            for i in range(task_num):
                task = tasks[i]
                task["task_status"] = TaskStatus.COMPLETED
                task["task_result"] = f"task {i} completed"
                data = {
                    "task_id": task["task_id"],
                    "term": curr_term,
                    "task_status": task["task_status"],
                    "task_result": task["task_result"],
                }
                async with session.put(
                    dbserver_url + "/task/status", json=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"]

            for i in range(task_num):
                task = tasks[i]
                data = {
                    "task_id": task["task_id"],
                }
                async with session.get(dbserver_url + "/task", params=data) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"], body["err"]

                    assert body["term"] == curr_term
                    assert body["task_agent"] == task["task_agent"]
                    assert body["task_status"] == TaskStatus.COMPLETED
                    assert body["task_name"] == task["task_name"]
                    assert body["task_description"] == task["task_description"]
                    assert body["task_result"] == task["task_result"]

            # (failed) update task status
            for i in range(task_num):
                data = {
                    "task_id": task["task_id"],
                    "term": prev_term,
                    "task_status": TaskStatus.ABORTED,
                    "task_result": f"task {i} aborted",
                }
                async with session.put(
                    dbserver_url + "/task/status", json=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert not body["success"]
                    assert body["err"] is not None

    finally:
        await logger.stop()
        dbserver_process.terminate()
        dbserver_process.join()
        os.remove(db_file)
