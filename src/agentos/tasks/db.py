import aiosqlite

from agentos.tasks.elem import TaskStatus

DB_FILE = "agentos.db"


class AgentDatabase:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file

    async def init_db(self):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                """
            CREATE TABLE IF NOT EXISTS Tasks (
                task_id INTEGER PRIMARY KEY,
                term INTEGER NOT NULL,
                task_agent TEXT NOT NULL,
                task_status TEXT NOT NULL,
                task_type TEXT NOT NULL,
                task_description TEXT NOT NULL,
                task_result TEXT NOT NULL
            )"""
            )

            await db.execute(
                """
            CREATE TABLE IF NOT EXISTS Progress (
                task_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                term INTEGER NOT NULL,
                result TEXT NOT NULL,
                PRIMARY KEY (task_id, round),
                FOREIGN KEY (task_id) REFERENCES Tasks(task_id)
            )"""
            )

            await db.commit()

    async def create_task(self, task_agent, task_type, task_description) -> int | None:
        async with aiosqlite.connect(self.db_file) as db:
            cursor = await db.execute(
                "INSERT INTO Tasks (term, task_agent, task_status, task_type, task_description, task_result) VALUES (0, ?, ?, ?, ?, ?)",
                (task_agent, TaskStatus.PENDING, task_type, task_description, ""),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_task(self, task_id):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                "SELECT term, task_agent, task_status, task_type, task_description, task_result FROM Tasks WHERE task_id = ?",
                (task_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row

    async def get_agent_tasks(self, task_agent):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                """
                SELECT 
                    task_id, term, task_agent, task_status, task_type, task_description, task_result 
                FROM Tasks
                WHERE task_agent = ?
                ORDER BY
                    task_id ASC
                """,
                (task_agent,),
            ) as cursor:
                rows = await cursor.fetchall()
                return rows

    async def update_task_status(self, task_id, term, task_status, task_result) -> bool:
        async with aiosqlite.connect(self.db_file) as db:
            cursor = await db.execute(
                """
                UPDATE Tasks 
                SET term = ?, task_status = ?, task_result = ? 
                WHERE task_id = ? AND ? >= term
                """,
                (term, task_status, task_result, task_id, term),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def save_progress(self, task_id, round, term, result) -> bool:
        async with aiosqlite.connect(self.db_file) as db:
            should_update = False
            await db.execute("PRAGMA foreign_keys = ON")
            async with db.execute(
                "SELECT term FROM Progress WHERE task_id = ? AND round = ?",
                (task_id, round),
            ) as cursor:
                row = await cursor.fetchone()
                if row is None or term > row[0]:
                    should_update = True

            if should_update:
                await db.execute(
                    "INSERT OR REPLACE INTO Progress (task_id, round, term, result) VALUES (?, ?, ?, ?)",
                    (task_id, round, term, result),
                )
                await db.commit()

            return should_update

    async def get_progress_list(self, task_id):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            async with db.execute(
                """
                SELECT 
                    round, term, result 
                FROM Progress 
                WHERE task_id = ?
                ORDER BY
                    round ASC
                """,
                (task_id,),
            ) as cursor:
                return await cursor.fetchall()
