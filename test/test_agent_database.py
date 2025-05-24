""
# Required libraries for this test file:
# - pytest: for discovering and running test cases
# - pytest-asyncio: to support async test functions (e.g., async def)
# - pytest_asyncio.fixture: for creating async-compatible fixtures
# - aiosqlite: async SQLite driver used in AgentDatabase

# Install using:
# pip install pytest pytest-asyncio aiosqlite

""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import pytest
import pytest_asyncio
import aiosqlite

# Weiser, change this, I couldn't use global. I think we need to change the name of the global.py if we want to import it in different file
from databasecode import AgentDatabase  # the AgentDatabase in databasecode.py in the same folder of this test file

TEST_DB = "test_agentos.db"

# ──────────────────────── FIXED ASYNC FIXTURE ─────────────────────────
@pytest_asyncio.fixture(scope="module")
async def setup_db():
    db = AgentDatabase(TEST_DB)
    await db.init_db()
    yield db
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

# ──────────────────────── Document Table ─────────────────────────
@pytest.mark.asyncio
async def test_document_crud(setup_db):
    db = setup_db
    doc_id = await db.store_document("pdf", "test content")
    assert isinstance(doc_id, int)

    content = await db.get_document(doc_id)
    assert content == "test content"

    deleted = await db.delete_document(doc_id)
    assert deleted

    missing = await db.get_document(doc_id)
    assert missing is None

# ──────────────────────── Task Table ─────────────────────────────
@pytest.mark.asyncio
async def test_task_crud(setup_db):
    db = setup_db
    task_id = await db.create_task(42, "classification", "do classification task")
    assert isinstance(task_id, int)

    task = await db.get_task(task_id)
    assert task == (42, "classification", "do classification task")

    desc = await db.get_task_description(task_id)
    assert desc == "do classification task"

    updated = await db.update_task_type(task_id, "segmentation")
    assert updated

    task = await db.get_task(task_id)
    assert task[1] == "segmentation"

    updated_desc = await db.update_task_description(task_id, 1, 2, "updated task description")
    assert updated_desc is True

    desc = await db.get_task_description(task_id)
    assert desc == "updated task description"

    deleted = await db.delete_task(task_id)
    assert deleted
    assert await db.get_task(task_id) is None

# ──────────────────────── Progress Table ─────────────────────────
@pytest.mark.asyncio
async def test_progress_crud(setup_db):
    db = setup_db
    task_id = await db.create_task(1, "type", "description")
    node_id = "node-a"

    saved = await db.save_progress(task_id, node_id, "result-v1", 0, 1)
    assert saved

    row = await db.get_progress(task_id, node_id)
    assert row[4] == "result-v1"

    await db.save_progress(task_id, node_id, "result-old", 0, 0)
    row = await db.get_progress(task_id, node_id)
    assert row[4] == "result-v1"

    await db.save_progress(task_id, node_id, "result-v2", 1, 2)
    row = await db.get_progress(task_id, node_id)
    assert row[4] == "result-v2"

    progresses = await db.get_progress_list(task_id)
    assert len(progresses) == 1

    deleted = await db.delete_progress(task_id, node_id)
    assert deleted
    assert await db.get_progress(task_id, node_id) is None

# ──────────────────────── Edge Cases ─────────────────────────────
@pytest.mark.asyncio
async def test_update_nonexistent_task_description(setup_db):
    db = setup_db
    response = await db.update_task_description(9999, 1, 2, "new desc")
    assert response == "Task not found"

@pytest.mark.asyncio
async def test_save_progress_reject_old_epochs(setup_db):
    db = setup_db
    task_id = await db.create_task(2, "type", "desc")
    node_id = "node-b"

    await db.save_progress(task_id, node_id, "newest", 5, 6)
    await db.save_progress(task_id, node_id, "oldest", 4, 3)

    row = await db.get_progress(task_id, node_id)
    assert row[4] == "newest"

@pytest.mark.asyncio
async def test_save_progress_equal_global_lower_regional(setup_db):
    db = setup_db
    task_id = await db.create_task(3, "type", "desc")
    node_id = "node-c"

    await db.save_progress(task_id, node_id, "first", 2, 5)
    await db.save_progress(task_id, node_id, "should_not_update", 2, 2)

    row = await db.get_progress(task_id, node_id)
    assert row[4] == "first"

@pytest.mark.asyncio
async def test_get_progress_list_empty(setup_db):
    db = setup_db
    task_id = await db.create_task(4, "type", "desc")
    progresses = await db.get_progress_list(task_id)
    assert progresses == []

@pytest.mark.asyncio
async def test_save_progress_invalid_task_id(setup_db):
    db = setup_db
    try:
        await db.save_progress(9999, "ghost-node", "data", 1, 1)
        assert False, "Expected IntegrityError due to foreign key"
    except aiosqlite.IntegrityError:
        pass
