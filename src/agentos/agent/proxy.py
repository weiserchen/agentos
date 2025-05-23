import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict

import aiohttp
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

from agentos.config import API_KEY, API_MODEL
from agentos.scheduler import FIFOPolicy, QueueTask
from agentos.tasks.coordinator import SingleNodeCoordinator
from agentos.tasks.elem import AgentCallTaskEvent, CoordinatorTaskEvent
from agentos.tasks.executor import AgentInfo
from agentos.tasks.generate_task import get_task_node
from agentos.utils.logger import AsyncLogger


class Agent:
    def __init__(
        self, api_key: str, api_model: str, temp: float = 0.7, max_tokens: int = 2000
    ):
        self.api_key = api_key
        self.api_model = api_model
        self.temp = temp
        self.max_tokens = max_tokens

    async def call(self, prompt: str, stop):
        client = AsyncOpenAI(
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
        update_interval: int = 3,
        queue_cap: int = 10,
        sem_cap: int = 1,
    ):
        self.id = id
        self.my_url = ""
        self.gateway_url = gateway_url
        self.monitor_url = monitor_url
        self.update_interval = update_interval
        self.queue_cap = queue_cap
        self.sem_cap = sem_cap
        self.agent = Agent(API_KEY, API_MODEL)
        self.coord_map: Dict[int, SingleNodeCoordinator] = dict()
        self.agents_view: Dict[str, AgentInfo] = dict()
        self.policy = FIFOPolicy(100)
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(sem_cap)
        self.logger = AsyncLogger(id)

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

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        asyncio.create_task(self.update_membership())
        asyncio.create_task(self.execute_task())
        await self.logger.start()
        yield
        await self.logger.stop()

    async def ready(self):
        return {
            "status": "proxy ok",
        }

    async def handle_coordinator(self, e: CoordinatorTaskEvent):
        async def run_coordinator(coord: SingleNodeCoordinator):
            try:
                await coord.start()
                data = {
                    "task_id": coord.task_id,
                    "success": coord.success,
                    "result": coord.result,
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.gateway_url + "/task/update", json=data
                    ) as response:
                        if response.status >= 300:
                            await self.logger.error(
                                f"run_coordinator - task {coord.task_id} task update connection failed"
                            )
                            return

                        body = await response.json()
                        if not body["success"]:
                            await self.logger.error(
                                f"run_coordinator - task {coord.task_id} task update failed"
                            )
                            return

            except Exception:
                pass

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
                        e.task_id, task_node, self.agents_view
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
        return {"result": task.result}

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

    async def checkpoint(self):
        pass

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
                raise e

            await asyncio.sleep(self.update_interval)
