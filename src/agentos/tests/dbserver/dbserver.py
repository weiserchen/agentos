import logging
import multiprocessing as mp
import os

import pytest

from agentos.service.dbserver import AgentDatabaseServer
from agentos.tasks.elem import TaskStatus
from agentos.tasks.utils import http_get, http_post, http_put
from agentos.utils.logger import AsyncLogger
from agentos.utils.ready import is_url_ready

script_dir = os.path.dirname(os.path.abspath(__file__))
db_file = os.path.join(script_dir, "pytest.db")
dbserver = AgentDatabaseServer(db_file, log_level=logging.DEBUG)
dbserver_host = "127.0.0.1"
dbserver_port = 10002
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

        task_num = 10
        test_agent = "pytest"
        curr_term = 0
        default_round = -1
        default_term = 0
        default_result = ""
        default_status = TaskStatus.PENDING
        tasks = []
        for i in range(task_num):
            task = {
                "task_agent": test_agent,
                "task_name": f"db_task_{i}",
                "task_description": f"db_description_{i}",
            }
            task_id = None
            resp = await http_post(dbserver_url + "/task", task)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]
            task_id = body["task_id"]
            assert task_id is not None

            task["task_id"] = task_id
            task["round"] = default_round
            task["term"] = default_term
            task["task_status"] = default_status
            task["task_result"] = default_result
            tasks.append(task)

        data = {
            "task_id": 10000,
        }
        resp = await http_get(dbserver_url + "/task", data)
        assert resp["success"]
        body = resp["body"]
        assert not body["success"]
        assert body["err"] is not None

        for i in range(task_num):
            task = tasks[i]
            data = {
                "task_id": task["task_id"],
            }
            resp = await http_get(dbserver_url + "/task", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]

            assert body["round"] == task["round"]
            assert body["term"] == task["term"]
            assert body["task_agent"] == task["task_agent"]
            assert body["task_status"] == TaskStatus.PENDING
            assert body["task_name"] == task["task_name"]
            assert body["task_description"] == task["task_description"]
            assert body["task_result"] == task["task_result"]

        data = {
            "task_agent": "non-exist agent",
        }
        resp = await http_get(dbserver_url + "/tasks/agent", data)
        assert resp["success"]
        body = resp["body"]
        assert body["success"], body["err"]
        assert len(body["tasks"]) == 0

        data = {
            "task_agent": test_agent,
        }
        resp = await http_get(dbserver_url + "/tasks/agent", data)
        assert resp["success"]
        body = resp["body"]
        assert body["success"], body["err"]

        db_tasks = body["tasks"]
        assert len(db_tasks) == len(tasks)
        for i in range(task_num):
            task = tasks[i]
            db_task = db_tasks[i]

            assert db_task["task_id"] == task["task_id"]
            assert db_task["round"] == task["round"]
            assert db_task["term"] == task["term"]
            assert db_task["task_agent"] == task["task_agent"]
            assert db_task["task_status"] == TaskStatus.PENDING
            assert db_task["task_name"] == task["task_name"]
            assert db_task["task_description"] == task["task_description"]
            assert db_task["task_result"] == task["task_result"]

        curr_round = 0
        # update task progress (round 0)
        for i in range(task_num):
            task = tasks[i]
            task["task_result"] = f"task {i} round {curr_round} completed"
            data = {
                "task_id": task["task_id"],
                "round": curr_round,
                "term": curr_term,
                "task_status": TaskStatus.PENDING,
                "task_result": task["task_result"],
            }
            resp = await http_put(dbserver_url + "/task/status", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]

        # update term
        prev_term = -1
        curr_term = 1

        # (failed) update task progress
        for i in range(task_num):
            task = tasks[i]
            data = {
                "task_id": task["task_id"],
                "round": curr_round,
                "term": prev_term,
                "task_status": task["task_status"],
                "task_result": task["task_result"],
            }
            resp = await http_put(dbserver_url + "/task/status", data)
            assert resp["success"]
            body = resp["body"]
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
                "task_status": task["task_status"],
                "task_result": task["task_result"],
            }
            resp = await http_put(dbserver_url + "/task/status", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]

        curr_round = 2

        # mark all task as completed (round 2)
        for i in range(task_num):
            task = tasks[i]
            task["task_status"] = TaskStatus.COMPLETED
            task["task_result"] = f"task {i} completed"
            data = {
                "task_id": task["task_id"],
                "round": curr_round,
                "term": curr_term,
                "task_status": task["task_status"],
                "task_result": task["task_result"],
            }
            resp = await http_put(dbserver_url + "/task/status", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]

        for i in range(task_num):
            task = tasks[i]
            data = {
                "task_id": task["task_id"],
            }
            resp = await http_get(dbserver_url + "/task", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]

            assert body["round"] == curr_round
            assert body["term"] == curr_term
            assert body["task_agent"] == task["task_agent"]
            assert body["task_status"] == task["task_status"]
            assert body["task_name"] == task["task_name"]
            assert body["task_description"] == task["task_description"]
            assert body["task_result"] == task["task_result"]

        # (failed) update task status (expired term)
        for i in range(task_num):
            data = {
                "task_id": task["task_id"],
                "round": curr_round,
                "term": prev_term,
                "task_status": TaskStatus.ABORTED,
                "task_result": f"task {i} aborted",
            }
            resp = await http_put(dbserver_url + "/task/status", data)
            assert resp["success"]
            body = resp["body"]
            assert not body["success"]
            assert body["err"] is not None

        # (failed) update task status (not pending task)
        for i in range(task_num):
            data = {
                "task_id": task["task_id"],
                "round": curr_round,
                "term": curr_term,
                "task_status": TaskStatus.ABORTED,
                "task_result": f"task {i} aborted",
            }
            resp = await http_put(dbserver_url + "/task/status", data)
            assert resp["success"]
            body = resp["body"]
            assert not body["success"]
            assert body["err"] is not None

    finally:
        os.remove(db_file)
        await logger.stop()
        dbserver_process.terminate()
        dbserver_process.join()
