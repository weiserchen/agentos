import asyncio
import logging
import random
import sys
import traceback
from contextlib import asynccontextmanager
from typing import Dict

import uvicorn
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agentos.tasks.elem import TaskStatus
from agentos.tasks.executor import AgentInfo
from agentos.tasks.utils import http_get, http_post_with_exception, http_put
from agentos.utils.logger import AsyncLogger
from agentos.utils.sleep import random_sleep


class AgentStatusRequest(BaseModel):
    agent_info: AgentInfo | None


class AgentRecoveryServer:
    agents: Dict[str, AgentInfo]

    def __init__(
        self,
        monitor_url: str,
        dbserver_url: str,
        update_interval: int = 10,
        log_level: int = logging.WARNING,
    ):
        self.monitor_url = monitor_url
        self.dbserver_url = dbserver_url
        self.update_interval = update_interval
        self.agents = dict()
        self.recovering_set = set()
        self.lock = asyncio.Lock()
        self.log_level = log_level
        self.logger = AsyncLogger("recovery", level=log_level)

    async def ready(self):
        return {
            "status": "agent recovery ok",
        }

    async def get_agent(self) -> AgentInfo:
        async with self.lock:
            agent_list = list(self.agents.values())
            return random.choice(agent_list)

    async def recover_agent(self, agent: AgentInfo):
        MAX_RETRY = 3

        async def recover_task(task) -> bool:
            task["term"] += 1
            task["round"] += 1
            task_id = task["task_id"]
            round = task["round"]
            term = task["term"]
            task_name = task["task_name"]
            task_description = task["task_description"]
            task_result = task["task_result"]
            n_rounds = task["n_rounds"]
            n_samples = task["n_samples"]
            n_voters = task["n_voters"]
            data = {
                "task_id": task_id,
                "round": round,
                "term": term,
                "task_name": task_name,
                "task_description": task_description,
                "task_result": task_result,
                "n_rounds": n_rounds,
                "n_samples": n_samples,
                "n_voters": n_voters,
            }
            await self.logger.warning(f"recoverying task {task_id}")
            for i in range(MAX_RETRY):
                try:
                    new_agent = await self.get_agent()
                    await http_post_with_exception(
                        url=new_agent.addr + "/coordinator",
                        data=data,
                        name="recovery",
                    )

                    await self.logger.warning(f"[Task {task_id}] recovered")

                    return True

                except Exception as e:
                    if i == MAX_RETRY - 1:
                        await self.logger.error(
                            f"recover_agents - failed to retry task: {task_id} - exception: {e}"
                        )
                        return False
                    else:
                        await self.logger.error(
                            f"recover_agents - retrying task: {task_id} - exception: {e}"
                        )
                        await random_sleep(5)

        try:
            await self.logger.warning(f"recovering agent {agent.id}...")

            data = {
                "task_agent": agent.id,
            }
            resp = await http_get(self.dbserver_url + "/tasks/agent", data)
            assert resp["success"]
            body = resp["body"]
            assert body["success"], body["err"]
            tasks = body["tasks"]

            futures = []
            for task in tasks:
                futures.append(recover_task(task))

            outputs = await asyncio.gather(*futures)

            for i, ok in enumerate(outputs):
                if not ok:
                    task = tasks[i]
                    data = {
                        "task_id": task["task_id"],
                        "round": -1,
                        "term": task["term"],
                        "task_status": TaskStatus.ABORTED,
                        "task_result": "aborted",
                    }
                    try:
                        resp = await http_put(self.dbserver_url + "/task/status", data)
                        assert resp["success"]
                        body = resp["body"]
                        assert body["success"], body["err"]

                        await self.logger.warning(f"[Task {task['task_id']}] aborted")

                    except Exception as e:
                        await self.logger.error(f"recover_agents - exception: {e}")

            async with self.lock:
                self.recovering_set.remove(agent.id)

        except Exception as e:
            tb = sys.exc_info()[2]
            filename, lineno, func, text = traceback.extract_tb(tb)[-1]
            err_str = f"Exception in {filename}, line {lineno}: {text}"
            await self.logger.error(f"recover_agents - exception: {e} - {err_str}")

        finally:
            async with self.lock:
                self.recovering_set.discard(agent.id)

    async def update_membership(self):
        while True:
            try:
                resp = await http_get(self.monitor_url + "/agent/list")
                assert resp["success"]
                body = resp["body"]
                assert body["success"], body["err"]

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
                    for id, agent in self.agents.items():
                        if id not in new_agents:
                            if id not in self.recovering_set:
                                self.recovering_set.add(id)
                                asyncio.create_task(self.recover_agent(agent))

                    self.agents = new_agents

            except Exception as e:
                await self.logger.error(f"update_membership - exception: {e}")

            await random_sleep(self.update_interval)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.logger.start()
        asyncio.create_task(self.update_membership())
        yield
        await self.logger.stop()

    def run(self, host: str, port: int):
        router = APIRouter()
        router.get("/ready")(self.ready)
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
