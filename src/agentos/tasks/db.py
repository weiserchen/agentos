import os

import aiosqlite

from agentos.tasks.elem import TaskStatus

script_dir = os.path.dirname(__file__)
DB_FILE = os.path.join(script_dir, "agentos.db")


class AgentDatabase:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file

    async def init_db(self):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                """
            CREATE TABLE IF NOT EXISTS Tasks (
                task_id INTEGER PRIMARY KEY,
                round INTEGER NOT NULL,
                term INTEGER NOT NULL,
                task_agent TEXT NOT NULL,
                task_status TEXT NOT NULL,
                task_type TEXT NOT NULL,
                task_description TEXT NOT NULL,
                task_result TEXT NOT NULL,
                n_rounds INTEGER NOT NULL,
                n_samples INTEGER NOT NULL,
                n_voters INTEGER NOT NULL
            )"""
            )

            await db.commit()

    async def create_task(
        self,
        task_agent: str,
        task_type: str,
        task_description: str,
        n_rounds: int,
        n_samples: int,
        n_voters: int,
    ) -> int | None:
        async with aiosqlite.connect(self.db_file) as db:
            cursor = await db.execute(
                """INSERT INTO Tasks (
                        round, 
                        term, 
                        task_agent, 
                        task_status, 
                        task_type, 
                        task_description, 
                        task_result,
                        n_rounds,
                        n_samples,
                        n_voters
                    ) 
                    VALUES (-1, 0, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_agent,
                    TaskStatus.PENDING,
                    task_type,
                    task_description,
                    "",
                    n_rounds,
                    n_samples,
                    n_voters,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_task(self, task_id: int):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                """SELECT 
                        round, 
                        term, 
                        task_agent, 
                        task_status, 
                        task_type, 
                        task_description, 
                        task_result,
                        n_rounds,
                        n_samples,
                        n_voters
                    FROM Tasks WHERE task_id = ?
                """,
                (task_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row

    async def get_pending_agent_tasks(self, task_agent: str):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                """
                SELECT 
                    task_id, 
                    round, 
                    term, 
                    task_agent, 
                    task_status, 
                    task_type, 
                    task_description, 
                    task_result,
                    n_rounds,
                    n_samples,
                    n_voters
                FROM Tasks
                WHERE task_agent = ? AND task_status = ?
                ORDER BY
                    task_id ASC
                """,
                (task_agent, TaskStatus.PENDING),
            ) as cursor:
                rows = await cursor.fetchall()
                return rows

    async def update_pending_task_status(
        self,
        task_id: int,
        round: int,
        term: int,
        task_status: TaskStatus,
        task_result: str,
    ) -> int:
        async with aiosqlite.connect(self.db_file) as db:
            cursor = await db.execute(
                """
                UPDATE Tasks 
                SET round = ?, term = ?, task_status = ?, task_result = ? 
                WHERE task_id = ? AND ? >= term AND task_status = ?
                """,
                (
                    round,
                    term,
                    task_status,
                    task_result,
                    task_id,
                    term,
                    TaskStatus.PENDING,
                ),
            )
            await db.commit()
            return cursor.rowcount == 1
