import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict

import aiohttp
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

from agentos.config import (
    API_BASE,
    API_KEY,
    API_MODEL,
    LOCAL_API_BASE,
    LOCAL_API_KEY,
    LOCAL_MODEL,
    run_local,
)
from agentos.scheduler import FIFOPolicy, QueueTask
from agentos.tasks.coordinator import SingleNodeCoordinator
from agentos.tasks.elem import AgentCallTaskEvent, CoordinatorTaskEvent, TaskStatus
from agentos.tasks.executor import AgentInfo
from agentos.tasks.generate_task import get_task_node
from agentos.tasks.utils import http_post_with_exception, http_put_with_exception
from agentos.utils.logger import AsyncLogger


class Agent:
    def __init__(
        self,
        api_key: str,
        api_model: str,
        local_api_port: int,
        temp: float = 0.7,
        max_tokens: int = 2000,
    ):
        if run_local:
            self.api_base = LOCAL_API_BASE.format(port=local_api_port)
            self.api_key = LOCAL_API_KEY
            self.api_model = LOCAL_MODEL
        else:
            self.api_base = API_BASE
            self.api_key = api_key
            self.api_model = api_model
        self.temp = temp
        self.max_tokens = max_tokens

    async def call(self, prompt: str, stop):
        client = None
        if self.api_base == "":
            client = AsyncOpenAI(
                api_key=self.api_key,
            )
        else:
            client = AsyncOpenAI(
                base_url=self.api_base,
                api_key=self.api_key,
            )

        res = await client.chat.completions.create(
            model=self.api_model,
            temperature=self.temp,
            max_tokens=self.max_tokens,
            stop=stop,
            messages=[{"role": "user", "content": prompt}],
        )

        content = res.choices[0].message.content
        return content


class AgentProxy:
    def __init__(
        self,
        id: str,
        gateway_url: str,
        monitor_url: str,
        dbserver_url: str,
        local_api_port: int = 8000,
        persistence: bool = True,
        update_interval: int = 3,
        queue_cap: int = 10,
        sem_cap: int = 1,
    ):
        self.id = id
        self.my_url = ""
        self.gateway_url = gateway_url
        self.monitor_url = monitor_url
        self.dbserver_url = dbserver_url
        self.persistence = persistence
        self.update_interval = update_interval
        self.queue_cap = queue_cap
        self.sem_cap = sem_cap
        self.agent = Agent(API_KEY, API_MODEL, local_api_port)
        self.coord_map: Dict[int, SingleNodeCoordinator] = dict()
        self.agents_view: Dict[str, AgentInfo] = dict()
        self.policy = FIFOPolicy(queue_cap)
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(sem_cap)
        self.logger = AsyncLogger(id)

    async def ready(self):
        return {
            "status": "proxy ok",
        }

    async def handle_coordinator(self, e: CoordinatorTaskEvent):
        async def run_coordinator(coord: SingleNodeCoordinator):
            try:
                async for _ in coord.run():
                    if self.persistence:
                        status_data = {
                            "task_id": coord.task_id,
                            "round": coord.round,
                            "term": coord.term,
                            "task_status": TaskStatus.COMPLETED
                            if coord.completed
                            else TaskStatus.PENDING,
                            "task_result": coord.result,
                        }
                        await http_put_with_exception(
                            url=self.dbserver_url + "/task/status",
                            data=status_data,
                            name="db task status",
                        )

                    gw_data = {
                        "task_id": coord.task_id,
                        "round": coord.round,
                        "term": coord.term,
                        "completed": coord.completed,
                        "success": coord.success,
                        "result": coord.result,
                    }
                    await http_post_with_exception(
                        url=self.gateway_url + "/task/update",
                        data=gw_data,
                        name="gateway",
                    )

            except Exception as e:
                await self.logger.error(
                    f"run_coordinator - task {coord.task_id} task update failed: {e}"
                )

        async def get_agents() -> Dict[str, AgentInfo]:
            async with self.lock:
                return self.agents_view

        try:
            coord = None
            await self.logger.debug(
                f"coordinator - \ntask_name: {e.task_name}\ntask_description: {e.task_description}"
            )
            async with self.lock:
                if e.task_id not in self.coord_map:
                    task_node = get_task_node(e.task_name, e.task_description)
                    await self.logger.debug(
                        f"coordinator - task_node - {str(task_node)}"
                    )
                    self.coord_map[e.task_id] = SingleNodeCoordinator(
                        e.task_id,
                        e.round,
                        e.term,
                        e.task_result,
                        task_node,
                        get_agents,
                    )
                coord = self.coord_map[e.task_id]

            asyncio.create_task(run_coordinator(coord))
            return {
                "success": True,
            }

        except Exception as e:
            await self.logger.error(f"coordinator - exception: {e}")
            raise e

    async def call_agent(self, e: AgentCallTaskEvent):
        task = QueueTask(e)
        await self.policy.push(task)
        await task.wait()
        return {
            "result": task.result,
        }

    async def execute_task(self):
        async def run_task(task: QueueTask, prompt: str, stop: Any):
            try:
                await self.logger.info("calling agent...")
                res = await self.agent.call(prompt, stop)
                await task.set_result(res)
            except Exception as e:
                await self.logger.error(f"task failed: {e}")
            finally:
                self.semaphore.release()

        while True:
            await self.semaphore.acquire()

            task = await self.policy.pop()
            if task is None:
                self.semaphore.release()
                await asyncio.sleep(0.5)
                continue

            event: AgentCallTaskEvent = task.task_event
            await self.logger.info(
                f"execute_task - id:{event.task_id}, round:{event.task_round}, action: {event.task_action}"
            )
            prompt = event.task_description
            stop = event.task_stop
            asyncio.create_task(run_task(task, prompt, stop))

    async def membership_view(self):
        async with self.lock:
            return {
                "agents": self.agents_view,
            }

    async def update_membership(self):
        while True:
            data = {
                "agent_info": {
                    "id": self.id,
                    "addr": self.my_url,
                    "workload": await self.policy.workload(),
                },
            }
            await self.logger.info(f"heartbeat - {data}")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.monitor_url + "/agent", json=data
                    ) as response:
                        # ignore unsuccessful updates
                        if response.status < 300:
                            body = await response.json()
                            if body["success"]:
                                new_agents_view = dict()
                                for id, member in body["members"].items():
                                    agent_info = AgentInfo(
                                        id=member["id"],
                                        addr=member["addr"],
                                        workload=member["workload"],
                                    )
                                    new_agents_view[id] = agent_info

                                async with self.lock:
                                    self.agents_view = new_agents_view

            except HTTPException as e:
                await self.logger.error(f"HTTP exception: {e}")
            except Exception as e:
                await self.logger.error(f"exception: {e}")
                raise e

            await asyncio.sleep(self.update_interval)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        asyncio.create_task(self.update_membership())
        asyncio.create_task(self.execute_task())
        await self.logger.start()
        yield
        await self.logger.stop()

    def run(self, domain: str, host: str, port: int):
        self.my_url = f"http://{domain}:{port}"
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/membership/view")(self.membership_view)
        router.post("/coordinator")(self.handle_coordinator)
        router.post("/agent/call")(self.call_agent)
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

        uvicorn.run(app, host=host, port=port)
