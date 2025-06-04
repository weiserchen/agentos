import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agentos.tasks.db import AgentDatabase
from agentos.utils.logger import AsyncLogger


class CreateTaskReq(BaseModel):
    task_agent: str
    task_name: str
    task_description: str


class UpdateTaskStatusReq(BaseModel):
    task_id: int
    round: int
    term: int
    task_status: str
    task_result: str


class AgentDatabaseServer:
    def __init__(self, db_file, log_level: int = logging.WARNING):
        self.db = AgentDatabase(db_file)
        self.lock = asyncio.Lock()
        self.log_level = log_level
        self.logger = AsyncLogger("dbserver", level=log_level)

    async def ready(self):
        return {
            "status": "db server ok",
        }

    async def create_task(self, req: CreateTaskReq):
        result = {
            "success": False,
        }
        try:
            task_id = await self.db.create_task(
                req.task_agent,
                req.task_name,
                req.task_description,
            )

            if task_id is None:
                result["err"] = "create_task - db error: task id is None"
            else:
                result["success"] = True
                result["task_id"] = task_id

        except Exception as e:
            err_str = f"create_task - exception: {e}"
            await self.logger.error(err_str)
            result["err"] = err_str

        finally:
            return result

    async def update_pending_task_status(self, req: UpdateTaskStatusReq):
        await self.logger.info(f"update status - {req}")

        result = {
            "success": False,
        }
        try:
            ok = await self.db.update_pending_task_status(
                req.task_id,
                req.round,
                req.term,
                req.task_status,
                req.task_result,
            )

            if not ok:
                result["err"] = "update_task_status - db error: probably term expires"

            result["success"] = ok

        except Exception as e:
            err_str = f"update_task_status - exception: {e}"
            await self.logger.error(err_str)
            result["err"] = err_str

        finally:
            return result

    async def get_task(self, task_id: int):
        result = {
            "success": False,
        }
        try:
            row = await self.db.get_task(
                task_id,
            )

            if row is None:
                result["err"] = "get_task - db error: empty row"
            else:
                result["round"] = row[0]
                result["term"] = row[1]
                result["task_agent"] = row[2]
                result["task_status"] = row[3]
                result["task_name"] = row[4]
                result["task_description"] = row[5]
                result["task_result"] = row[6]
                result["success"] = True

        except Exception as e:
            err_str = f"get_task - exception: {e}"
            await self.logger.error(err_str)
            result["err"] = err_str

        finally:
            return result

    async def get_pending_agent_tasks(self, task_agent: str):
        result = {
            "success": False,
        }
        try:
            rows = await self.db.get_pending_agent_tasks(
                task_agent,
            )

            agent_tasks = []
            for row in rows:
                task = {}
                task["task_id"] = row[0]
                task["round"] = row[1]
                task["term"] = row[2]
                task["task_agent"] = row[3]
                task["task_status"] = row[4]
                task["task_name"] = row[5]
                task["task_description"] = row[6]
                task["task_result"] = row[7]
                agent_tasks.append(task)

            result["tasks"] = agent_tasks
            result["success"] = True

        except Exception as e:
            err_str = f"get_agent_tasks - exception: {e}"
            await self.logger.error(err_str)
            result["err"] = err_str

        finally:
            return result

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.logger.start()
        await self.db.init_db()
        yield
        await self.logger.stop()

    def run(self, host: str, port: int):
        router = APIRouter()
        router.get("/ready")(self.ready)
        router.get("/task")(self.get_task)
        router.post("/task")(self.create_task)
        router.get("/tasks/agent")(self.get_pending_agent_tasks)
        router.put("/task/status")(self.update_pending_task_status)
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
