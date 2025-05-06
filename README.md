# Agent OS: A Coordination middleware for large-scale AI Agent Cluster

## Install
```bash
# virtual env
python3 -m venv virtenv
source ./virtenv/bin/activate

# dependencies
pip install fastapi uvicorn
```

## Run
```bash
python src/main.py
```

## Database API

### Document Table

This table stores the request and response of queries.

- `doc_content` is the content of the document. It could be the query or the response of a query.

```sql
CREATE TABLE IF NOT EXISTS Documents (
	doc_id INTEGER PRIMARY KEY,
    doc_type TEXT NOT NULL,
    doc_content TEXT NOT NULL
);
```

API:
- `get_document(doc_id) -> doc_content`
- `store_document(doc_type, doc_content) -> doc_id`
- `delete_document(doc_id) -> ok` (optional)

### Task Table

The task table stores the metadata of a task.

- `task_type` is a reserved field
- `global_epoch` stores which region owns the task
- `regional_epoch` stores which agent proxy owns the task
- `task_description` stores the description of a task. It contains the task graph and other task information. It is a json object

```sql
CREATE TABLE IF NOT EXISTS Tasks (
	task_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    global_epoch INTEGER NOT NULL,
    regional_epoch INTEGER NOT NULL,
    task_description TEXT NOT NULL
);
```

Epoch comparison:
- Let p1 (old), p2 (new) as two objects
- p2 > p1 if
    - p2.global_epoch >= p1.global_epoch and
    - p2.regional_epoch > p1.global_epoch

API:
- `create_task(user_id, task_type, task_description) -> task_id`
- `get_task(task_id) -> (user_id, task_type, task_description)` (optional)
- `get_task_description(task_id) -> task_description`
- `update_task_type(task_id, task_type) -> ok` (optional)
- `update_task_description(task_id, global_epoch, regional_epoch, task_description) -> ok`
    - It performs the update only when the t2 (new) > t1 (old)
- `delete_task(task_id) -> ok` (optional)

### Progress Table

The Progress Table stores the progress of each node execition.

- `node_id` is the id of the node. In the task graph, each node will be labeled with an id
- `task_id` is the id of the task. It refers to the task in the Task Table
- `global_epoch` stores which region owns the task
- `regional_epoch` stores which agent proxy owns the task
- `result` stores the result of a node execution. It is a json object

```sql
CREATE TABLE IF NOT EXISTS Progress (
    task_id INTEGER NOT NULL,
	node_id TEXT NOT NULL,
    global_epoch INTEGER NOT NULL,
    regional_epoch INTEGER NOT NULL,
    result TEXT NOT NULL,
    PRIMARY KEY (task_id, node_id),
    FOREIGN KEY (task_id) REFERENCES Tasks (task_id)
);
```

API:
- `save_progress(task_id, node_id, result) -> ok`
    - It should save the progress when p2 (new) > p1 (old)
- `get_progress(task_id, node_id) -> (task_id, node_id, global_epoch, regional_epoch, result)`
    - It gets the progress with the largest (global_epoch, regional_epoch) pair
- `get_progress_list(task_id) -> [](task_id, node_id, global_epoch, regional_epoch, result)`
- `delete_progress(task_id, node_id) -> ok`