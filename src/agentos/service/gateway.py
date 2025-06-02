import asyncio
import random
from contextlib import asynccontextmanager
from typing import Dict

import aiohttp
import uvicorn
from fastapi import APIRouter, FastAPI

from agentos.tasks.elem import TaskQueryEvent, TaskStatus, TaskUpdateEvent
from agentos.tasks.executor import AgentInfo
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
    def __init__(self, monitor_url: str, dbserver_url: str):
        self.monitor_url = monitor_url
        self.dbserver_url = dbserver_url
        self.task_map: Dict[int, TaskResult] = dict()
        self.lock = asyncio.Lock()
        self.agents: Dict[str, AgentInfo] = dict()
        self.logger = AsyncLogger("gateway")
        self.lock = asyncio.Lock()

    async def ready(self):
        return {
            "status": "gateway ok",
        }

    async def query(self, e: TaskQueryEvent):
        try:
            async with aiohttp.ClientSession() as session:
                agent = pick_random_agent(self.agents)
                db_data = {
                    "task_agent": agent.id,
                    "task_name": e.task_name,
                    "task_description": e.task_description,
                }
                task_id = None
                async with session.post(
                    self.dbserver_url + "/task", json=db_data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"]
                    task_id = body["task_id"]
                    assert task_id is not None

                await self.logger.debug(f"task {task_id} created")

                data = {
                    "task_id": task_id,
                    "round": 0,
                    "term": 0,
                    "task_name": e.task_name,
                    "task_description": e.task_description,
                    "task_result": "",
                }
                await self.logger.debug(f"query - {data}")
                async with session.post(
                    agent.addr + "/coordinator", json=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
                    assert body["success"]
                    self.task_map[task_id] = TaskResult(task_id)
                    return {
                        "success": True,
                        "task_id": task_id,
                    }

        except Exception as err:
            await self.logger.error(f"query - exception: {err}")
            return {
                "success": False,
            }

    async def task_update(self, e: TaskUpdateEvent):
        await self.logger.info(f"update status - {e}")

        async with self.lock:
            if e.task_id not in self.task_map:
                return {
                    "success": False,
                }

            if e.completed:
                self.task_map[e.task_id].mark_complete(e.success, e.result)
            else:
                self.task_map[e.task_id].update(e.term, e.round, e.result)

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
            async with aiohttp.ClientSession() as session:
                data = {
                    "task_id": task_id,
                }
                async with session.put(
                    self.dbserver_url + "/task", params=data
                ) as response:
                    assert response.status < 300
                    body = await response.json()
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
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self.monitor_url + "/agent/list"
                    ) as response:
                        assert response.status < 300
                        body = await response.json()
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
        uvicorn.run(app, host=host, port=port)
