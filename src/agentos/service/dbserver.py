import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
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
    term: int
    task_status: str
    task_result: str


class UpdateTaskProgressReq(BaseModel):
    task_id: int
    round: int
    term: int
    result: str


class AgentDatabaseServer:
    def __init__(self, db_file):
        self.db = AgentDatabase(db_file)
        self.lock = asyncio.Lock()
        self.logger = AsyncLogger("dbserver")

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

    async def update_task_status(self, req: UpdateTaskStatusReq):
        result = {
            "success": False,
        }
        try:
            ok = await self.db.update_task_status(
                req.task_id,
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
                result["term"] = row[0]
                result["task_agent"] = row[1]
                result["task_status"] = row[2]
                result["task_name"] = row[3]
                result["task_description"] = row[4]
                result["task_result"] = row[5]
                result["success"] = True

        except Exception as e:
            err_str = f"get_task - exception: {e}"
            await self.logger.error(err_str)
            result["err"] = err_str

        finally:
            return result

    async def get_agent_tasks(self, task_agent: str):
        result = {
            "success": False,
        }
        try:
            rows = await self.db.get_agent_tasks(
                task_agent,
            )

            agent_tasks = []
            for row in rows:
                task = {}
                task["task_id"] = row[0]
                task["term"] = row[1]
                task["task_agent"] = row[2]
                task["task_status"] = row[3]
                task["task_name"] = row[4]
                task["task_description"] = row[5]
                task["task_result"] = row[6]
                agent_tasks.append(task)

            result["tasks"] = agent_tasks
            result["success"] = True

        except Exception as e:
            err_str = f"get_agent_tasks - exception: {e}"
            await self.logger.error(err_str)
            result["err"] = err_str

        finally:
            return result

    async def update_task_progress(self, req: UpdateTaskProgressReq):
        result = {
            "success": False,
        }
        try:
            await self.logger.info(f"[Task {req.task_id}] updating task progress...")
            ok = await self.db.save_progress(
                req.task_id,
                req.round,
                req.term,
                req.result,
            )

            if not ok:
                result["err"] = "update_task_progress - db error: probably term expires"

            result["success"] = ok

        except Exception as e:
            err_str = f"update_task_progress - exception: {e}"
            await self.logger.error(err_str)
            result["err"] = err_str

        finally:
            return result

    async def get_task_progress_list(self, task_id: int):
        result = {
            "success": False,
        }
        try:
            rows = await self.db.get_progress_list(
                task_id,
            )

            progress_list = []
            for row in rows:
                progress = {}
                progress["round"] = row[0]
                progress["term"] = row[1]
                progress["result"] = row[2]
                progress_list.append(progress)

            result["progress_list"] = progress_list
            result["success"] = True

        except Exception as e:
            err_str = f"get_task_progress_list - exception: {e}"
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
        router.get("/tasks/agent")(self.get_agent_tasks)
        router.get("/task/progress/list")(self.get_task_progress_list)
        router.post("/task")(self.create_task)
        router.post("/task/progress")(self.update_task_progress)
        router.put("/task/status")(self.update_task_status)
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
