import asyncio
import random
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

from agentos.config import API_KEY, API_MODEL
from agentos.scheduler import FIFOPolicy, QueueTask
from agentos.tasks.coordinator import TaskGraphCoordinator
from agentos.tasks.elem import AgentCallTaskEvent, TaskEvent
from agentos.tasks.executor import AgentInfo
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
        # print(content + "\n==================================\n")
        return content


class AgentProxy:
    def __init__(self, id: str, monitor_url: str, update_interval: int = 3):
        self.id = id
        self.my_url = ""
        self.coord_map = dict()
        self.agents_view = dict()
        self.local_random = random.Random()
        self.doc_map = dict()
        self.monitor_url = monitor_url
        self.policy = FIFOPolicy(100)
        self.lock = asyncio.Lock()
        self.agent = Agent(API_KEY, API_MODEL)
        self.update_interval = update_interval
        self.logger = AsyncLogger(id)

    def run(self, host: str, port: int):
        self.my_url = f"http://{host}:{port}"
        print(f"proxy: {self.my_url}")
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

    async def handle_coordinator(self, e: TaskEvent) -> bool:
        coord = None
        async with self.lock:
            if e.task_id not in self.coord_map:
                self.coord_map[e.task_id] = TaskGraphCoordinator("")
            coord = self.coord_map[e.task_id]

        asyncio.create_task(coord.process_event(e))
        return {
            "success": True,
        }

    async def call_agent(self, e: AgentCallTaskEvent):
        # print(e)
        task = QueueTask(e)
        await self.policy.push(task)
        await task.wait()
        return {"result": task.result}

    async def execute_task(self):
        while True:
            task = await self.policy.pop()
            # print(f'task: {task}')
            if task is None:
                await asyncio.sleep(0.1)
                continue

            prompt = task.task_event.task_description
            stop = task.task_event.task_stop
            res = await self.agent.call(prompt, stop)
            await task.set_result(res)

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
