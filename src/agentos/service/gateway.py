import asyncio
import logging
import random
from contextlib import asynccontextmanager
from typing import Dict

import uvicorn
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse

from agentos.tasks.elem import TaskQueryEvent, TaskStatus, TaskUpdateEvent
from agentos.tasks.executor import AgentInfo
from agentos.tasks.utils import http_get, http_post, http_put
from agentos.utils.logger import AsyncLogger
from agentos.utils.sleep import random_sleep


def pick_random_agent(agents: Dict[str, AgentInfo]) -> AgentInfo:
    agent_list = list(agents.values())
    return random.choice(agent_list)


class TaskResult:
    def __init__(self, task_id: int):
        self.task_id = task_id
        self.completed = False
        self.success = False
        self.term = 0
        self.round = -1
        self.result = ""
        self.status = TaskStatus.PENDING

    def update(self, term: int, round: int, result: str) -> bool:
        if term < self.term:
            return False

        if round <= self.round:
            return False

        self.term = term
        self.round = round
        self.result = result

    def mark_complete(self, success: bool, result: str):
        self.completed = True
        self.success = success
        self.result = result
        self.status = TaskStatus.COMPLETED

    def mark_aborted(self):
        self.completed = True
        self.success = False
        self.result = "aborted"
        self.status = TaskStatus.ABORTED


class AgentGatewayServer:
    def __init__(
        self, monitor_url: str, dbserver_url: str, log_level: int = logging.WARNING
    ):
        self.monitor_url = monitor_url
        self.dbserver_url = dbserver_url
        self.task_map: Dict[int, TaskResult] = dict()
        self.lock = asyncio.Lock()
        self.agents: Dict[str, AgentInfo] = dict()
        self.log_level = log_level
        self.logger = AsyncLogger("gateway", level=log_level)
        self.lock = asyncio.Lock()

    async def ready(self):
        return {
            "status": "gateway ok",
        }

    async def query(self, query_event: TaskQueryEvent):
        MAX_RETRIES = 3 
        for attempt in range(MAX_RETRIES):
            try:
                if not self.agents:
                    await self.logger.error("query - No agents available to process the task.")
                    return {"success": False, "err": "No agents available"}

                agent = pick_random_agent(self.agents)
                db_data = {
                    "task_agent": agent.id,
                    "task_name": query_event.task_name,
                    "task_description": query_event.task_description,
                    "n_rounds": query_event.n_rounds,
                    "n_samples": query_event.n_samples,
                    "n_voters": query_event.n_voters,
                }
                resp = await http_post(self.dbserver_url + "/task", db_data)
                assert resp["success"], f"DB task creation failed: {resp.get('error')}"
                body = resp["body"]
                assert body["success"], body["err"]
                task_id = body["task_id"]

                await self.logger.debug(f"Task {task_id} created, assigned to {agent.id}")

                data = {
                    "task_id": task_id,
                    "round": 0,
                    "term": 0,
                    "task_name": query_event.task_name,
                    "task_description": query_event.task_description,
                    "task_result": "",
                    "n_rounds": query_event.n_rounds,
                    "n_samples": query_event.n_samples,
                    "n_voters": query_event.n_voters,
                }

                resp = await http_post(agent.addr + "/coordinator", data)
                assert resp["success"], f"Proxy communication failed to {agent.id}: {resp.get('error')}"
                body = resp["body"]
                assert body["success"], body["err"]
                self.task_map[task_id] = TaskResult(task_id)
                return {
                    "success": True,
                    "task_id": task_id,
                }

            except Exception as err:
                await self.logger.warning(f"query - exception: (attempt {attempt + 1}/{MAX_RETRIES}) failed: {err}. Retrying with another agent...")
                if attempt >= MAX_RETRIES - 1:
                    await self.logger.error(f"Gateway query failed after {MAX_RETRIES} retries: {err}")
                    return {"success": False, "err": str(err)}
                await asyncio.sleep(0.5)

    async def task_update(self, update_event: TaskUpdateEvent):
        await self.logger.info(f"update status - {update_event}")

        async with self.lock:
            if update_event.task_id not in self.task_map:
                return {
                    "success": False,
                }

            if update_event.completed:
                self.task_map[update_event.task_id].mark_complete(
                    update_event.success,
                    update_event.result,
                )
            else:
                self.task_map[update_event.task_id].update(
                    update_event.term,
                    update_event.round,
                    update_event.result,
                )

            return {
                "success": True,
            }

    async def task_status(self, task_id: int):
        async with self.lock:
            if task_id in self.task_map:
                task_result = self.task_map[task_id]
                if not task_result.completed:
                    return {
                        "status": task_result.status,
                        "term": task_result.term,
                        "round": task_result.round,
                    }
                else:
                    return {
                        "status": task_result.status,
                        "success": task_result.success,
                        "result": task_result.result,
                    }

        try:
            data = {
                "task_id": task_id,
            }
            resp = http_put(self.dbserver_url + "/task", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]

            task_status = body["task_status"]
            success = body["success"]
            result = body["result"]
            term = body["term"]
            round = body["round"]
            result = TaskResult(task_id)
            if task_status == TaskStatus.COMPLETED:
                result.mark_complete(success, result)
            elif task_status == TaskStatus.PENDING:
                result.update(term, round, result)
            elif task_status == TaskStatus.ABORTED:
                result.mark_aborted()
            else:
                raise Exception("invalid state")

            async with self.lock:
                self.task_map[task_id] = result

            if not result.completed:
                return {
                    "status": result.status,
                    "term": result.term,
                    "round": result.round,
                }
            else:
                return {
                    "status": result.status,
                    "success": result.success,
                    "result": result.result,
                }

        except Exception as e:
            err_str = f"task_status - exception: {e}"
            await self.logger.error(err_str)
            return {
                "status": TaskStatus.NON_EXIST,
                "err": err_str,
            }

    async def update_membership(self):
        sleep_interval = 10
        while True:
            try:
                resp = await http_get(self.monitor_url + "/agent/list")
                assert resp["success"]
                body = resp["body"]
                assert body["success"]
                agents = body["agents"]
                new_agents = dict()
                for id, agent in agents.items():
                    agent_info = AgentInfo(
                        id=id,
                        addr=agent["addr"],
                        workload=agent["workload"],
                    )
                    new_agents[id] = agent_info

                await self.logger.debug(f"update_membership: {new_agents}")
                async with self.lock:
                    self.agents = new_agents

            except Exception as e:
                await self.logger.error(f"update_membership - exception: {e}")

            await random_sleep(sleep_interval)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.logger.start()
        asyncio.create_task(self.update_membership())
        yield
        await self.logger.stop()

    def run(self, host: str, port: int):
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/task/status")(self.task_status)
        router.post("/query")(self.query)
        router.post("/task/update")(self.task_update)
        app = FastAPI(lifespan=self.lifespan)
        app.include_router(router)

        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(
            request: Request, exc: RequestValidationError
        ):
            await self.logger.error(
                f"422 Validation Error on {request.method} {request.url}"
            )
            await self.logger.error(f"Detail: {exc.errors()}")
            await self.logger.error(f"Body: {exc.body}")
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors()},
            )

        @app.exception_handler(ResponseValidationError)
        async def response_validation_exception_handler(
            request: Request, exc: ResponseValidationError
        ):
            await self.logger.error(
                f"500 Response Validation Error on {request.method} {request.url}"
            )
            await self.logger.error(f"Detail: {exc.errors()}")
            return JSONResponse(
                status_code=500,
                content={"detail": exc.errors()},
            )

        uvicorn.run(app, host=host, port=port, log_level=self.log_level)
