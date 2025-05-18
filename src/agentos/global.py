import aiosqlite # type: ignore
import asyncio

DB_FILE = "agentos.db"

class AgentDatabase:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
    

    async def init_db(self):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Documents (
                doc_id INTEGER PRIMARY KEY,
                doc_type TEXT NOT NULL,
                doc_content TEXT NOT NULL
            )""")

            await db.execute("""
            CREATE TABLE IF NOT EXISTS Tasks (
                task_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                task_type TEXT NOT NULL,
                global_epoch INTEGER NOT NULL,
                regional_epoch INTEGER NOT NULL,
                task_description TEXT NOT NULL
            )""")

            await db.execute("""
            CREATE TABLE IF NOT EXISTS Progress (
                task_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                global_epoch INTEGER NOT NULL,
                regional_epoch INTEGER NOT NULL,
                result TEXT NOT NULL,
                PRIMARY KEY (task_id, node_id),
                FOREIGN KEY (task_id) REFERENCES Tasks(task_id)
            )""")

            await db.commit()

    async def get_document(self, doc_id):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT doc_content FROM Documents WHERE doc_id = ?", (doc_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
            
    async def store_document(self, doc_type, doc_content):
        async with aiosqlite.connect(self.db_file) as db:
            cursor = await db.execute("INSERT INTO Documents (doc_type, doc_content) VALUES (?, ?)", (doc_type, doc_content))
            await db.commit()
            return cursor.lastrowid
        
    async def delete_document(self, doc_id):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("DELETE FROM Documents WHERE doc_id = ?", (doc_id,))
            await db.commit()
            return True
       
    async def create_task(self, user_id, task_type, task_description):
        async with aiosqlite.connect(self.db_file) as db:
            cursor = await db.execute(
                "INSERT INTO Tasks (user_id, task_type, global_epoch, regional_epoch, task_description) VALUES (?, ?, 0, 0, ?)",
                (user_id, task_type, task_description))
            await db.commit()
            return cursor.lastrowid
    
    async def get_task(self, task_id):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT user_id, task_type, task_description FROM Tasks WHERE task_id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()
                return row if row else None

    async def get_task_description(self, task_id):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT task_description FROM Tasks WHERE task_id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def update_task_type(self, task_id, task_type):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute( "UPDATE Tasks SET task_type = ? WHERE task_id = ?",(task_type, task_id))
            await db.commit()
            return True
        
    async def update_task_description(self, task_id, new_global_epoch, new_regional_epoch, new_description):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT global_epoch, regional_epoch FROM Tasks WHERE task_id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return "Task not found"
                old_g, old_r = row
                if (new_global_epoch >= old_g) and (new_regional_epoch > old_g): # I'm not sure what do u mean by t2 (new) > t1 (old), so I assumed epoch global and regional
                    await db.execute("UPDATE Tasks SET global_epoch = ?, regional_epoch = ?, task_description = ? WHERE task_id = ?", 
                                     (new_global_epoch, new_regional_epoch, new_description, task_id))
                    await db.commit()
            return True

    async def delete_task(self, task_id):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("DELETE FROM Tasks WHERE task_id = ?", (task_id,))
            await db.commit()
            return True
            

    async def save_progress(self, task_id, node_id, result, global_epoch, regional_epoch): # I think you miss send global_epoch, regional_epoch in the github explaination so I assumed that we need them to compare
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            async with db.execute(
                "SELECT global_epoch, regional_epoch FROM Progress WHERE task_id = ? AND node_id = ?", 
                (task_id, node_id) 
            ) as cursor:
                row = await cursor.fetchone() # I returned both global_epoch, regional_epoch But in the logic we compare only with the global_epoch from github "p2.regional_epoch > p1.global_epoch"
                should_update = (not row) or (global_epoch >= row[0] and regional_epoch > row[0])

            if should_update:
                await db.execute("INSERT OR REPLACE INTO Progress (task_id, node_id, global_epoch, regional_epoch, result)VALUES (?, ?, ?, ?, ?)", 
                                 (task_id, node_id, global_epoch, regional_epoch, result))
                await db.commit()
            return True

    async def get_progress(self, task_id, node_id): 
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            async with db.execute("SELECT task_id, node_id, global_epoch, regional_epoch, result FROM Progress WHERE task_id = ? AND node_id = ?", (task_id, node_id)) as cursor:
                return await cursor.fetchone()

    async def get_progress_list(self, task_id):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            async with db.execute(" SELECT task_id, node_id, global_epoch, regional_epoch, result FROM Progress WHERE task_id = ?", (task_id,)) as cursor:
                return await cursor.fetchall()

    async def delete_progress(self, task_id, node_id):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("DELETE FROM Progress WHERE task_id = ? AND node_id = ?", (task_id, node_id))
            await db.commit()
            return True      





# # Test part 
#     # NEXT CODE Just for testing
#     async def get_full_document(self, doc_id):
#         async with aiosqlite.connect(self.db_file) as db:
#             async with db.execute("SELECT * FROM Documents WHERE doc_id = ?", (doc_id,)) as cursor:
#                 return await cursor.fetchone()
    
#     async def get_all_task(self):
#         async with aiosqlite.connect(self.db_file) as db:
#             async with db.execute("SELECT * FROM Tasks") as cursor:
#                 return await cursor.fetchall()
            
# # testing document table PASS THE TEST
# async def test_full_document_row():
#     db = AgentDatabase()
#     await db.init_db()

#     # Step 1: Insert a document
#     # doc_id = await db.store_document("text", "Waleed Alharbi;")
#     # print(f" Document inserted with ID: {doc_id}")
#     # doc_id = await db.delete_document(3)
#     # print(f" Document deleted with ID 1: {doc_id}")

#     # Step 2: Retrieve the full row
#     row = await db.get_full_document(3)

#     if row:
#         print("Full row returned:", row)
#         print(f"doc_id: {row[0]}")
#         print(f"doc_type: {row[1]}")
#         print(f"doc_content: {row[2]}")
#     else:
#         print("Document not found.")

# # testing task table
# async def test_task():
#     db = AgentDatabase()
#     await db.init_db()

#     # Step 1: Insert a document
#     #task_id = await db.create_task( 1, "search", "Looking for a number")
#     #print(f" task inserted with ID: {task_id}")
#     task_id = await db.delete_task(1)
#     print(f" Document deleted with ID 1: {task_id}")

#     # Step 2: Retrieve the full row
#     row = await db.get_task(task_id)
#     all_rows= await db.get_all_task()
    

#     if row:
#         print("Full row returned:", row)
#         print(f"user_id: {row[0]}")
#         print(f"task type: {row[1]}")
#         print(f"task describtion: {row[2]}")

#     else:
#         print("Document not found.")
    
#     print("Full TASKS :", all_rows)


# # Run the test
# if __name__ == "__main__":
#     #asyncio.run(test_full_document_row())
#     asyncio.run(test_task())
