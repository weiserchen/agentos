from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from typing import Dict, List, Tuple, Any
from agentos.tasks.elem import TaskEvent, AgentCallTaskEvent, TaskEventType
from agentos.tasks.executor import AgentInfo
from agentos.scheduler import FIFOPolicy, QueueTask
from agentos.tasks.graph import TaskGraphCoordinator
from openai import AsyncOpenAI
from dotenv import load_dotenv
from agentos.config import API_KEY, API_MODEL
import asyncio
import uvicorn
from uvicorn import Server, Config
import time
import aiohttp
import os
import random

class Agent:
    def __init__(self, api_key: str, api_model: str, temp: float = 0.7, max_tokens: int = 2000):
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
            messages=[{
                "role": "user", 
                "content": prompt
            }],
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

    def run(self, host: str, port: int):
        self.my_url = f'http://{host}:{port}'
        print(f"proxy: {self.my_url}")
        app = FastAPI()
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/membership/view")(self.membership_view)
        router.post("/coordinator")(self.handle_coordinator)
        router.post("/agent/call")(self.call_agent)
        app.include_router(router)

        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request: Request, exc: RequestValidationError):
            print(f"422 Validation Error on {request.method} {request.url}")
            print(f"Detail: {exc.errors()}")
            print(f"Body: {exc.body}")
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors()},
            )

        async def update_membership():
            await self.update_membership()

        async def execute_task():
            await self.execute_task()

        @app.on_event("startup")
        async def start_up():
            asyncio.create_task(update_membership())
            asyncio.create_task(execute_task())

        uvicorn.run(app, host=host, port=port)
        # config = Config(app=app, host=host, port=port)
        # server = Server(config)
        # server.run()

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
        return {
            "result": task.result
        }

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
            print(data)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.monitor_url+"/agent", json=data) as response:
                        # ignore unsuccessful updates
                        if response.status < 300:
                            body = await response.json()
                            if body['success']:
                                # print(body)
                                new_agents_view = dict()
                                for id, member in body['members'].items():
                                    agent_info = AgentInfo(
                                        id=member['id'],
                                        addr=member['addr'],
                                        workload=member['workload'],
                                    )
                                    new_agents_view[id] = agent_info

                                async with self.lock:
                                    self.agents_view = new_agents_view
                                
                                
                        
            except HTTPException:
                print(f'HTTP exception: {e}')
            except Exception as e:
                raise e
                
            await asyncio.sleep(self.update_interval)
