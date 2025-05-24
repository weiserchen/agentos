# Agent OS: A Coordination middleware for large-scale AI Agent Cluster

## Install
```bash
# virtual env
python3 -m venv virtenv
source ./virtenv/bin/activate

# dependencies
pip install -r requirements.txt
```

## Run
```bash
# service.py
cd src
python -m script.service

# client.py
# NOTE: 
# - client could fail due to some LLM uncertain output (e.g. using x-nano model)
# - client may reach OpenAI Token Per Minute (TPM) (e.g. running 3 code generations at the same time)
cd src
python -m script.client

# cleanup.py
# cleanup zombie processes after the test failed or some abnormal behavior observed
cd src
python script/cleanup.py
```

## Test
```bash
# -vvv: verbose output
# -s: real-time logging, not captured by the pytest
pytest -vvv -s test/proxy/proxy.py
pytest -vvv -s test/coordinator/gateway.py
```

## Troubleshooting
When the test behaves weirdly, possibly because of some uncollected zombie processes. Use command line commands to kill the zombie process.
```bash
ps -aux | grep python
kill -9 <PID>
```

## VSCode Settings
- `.vscode/settings.json`:
```json
{
    "[python]": {
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "always",
            "source.organizeImports.ruff": "always"
        },
        "editor.defaultFormatter": "charliermarsh.ruff"
    }
}
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

## Testing Client

Suppose we have 100 requests in the test suite:
- `send_req(url: str, req: Request)`:
    - This function send a requests to our system's url. It use asynchronous requests but not await. 
    - It follows the procedure:
        - First, it submits the request to our system and get a task id as the response.
        - Then, it loops and keeps sending the request to the task_status API to get the task status and response. For each loop, it sleeps for a short interal, such as 3 seconds (`asyncio.sleep()`).
        - Finally, it returns the task response if the task status becomes completed.
    - Besides executing the request, it also has to record the performance metrics.
        - It records the latency of each request.
        - The latency list is returned to the caller for aggregation.
- `send_all(url: str, req_list: List[Request])`:
    - This function send all requests to our system's url. It uses `send_req()` as the building block.
    - It may call `asyncio.gather()` to collect result from all requests.
- `send_in_interval(url: str, req_list: List[Request], interval_range: Tuple[int, int])`
    - This function simulates real traffic with intervals. Except for the first request, the client first sleeps for a random duration within the range. It then sends the request like before and gather all responses in the end.
- `send_batch_interval(url: str, req_list: List[Request], interval_range: Tuple[int, int], batch_size: int))`:
    - This function perform batching and simulates burst of traffic. Except for the first batch, the client first sleeps for a random duration with the range. It then sends requests in batch similar to the `send_all()`. It also gathers all responses in the end, not per batch.
- `send_dynamic_batch_interval(url: str, req_list: List[Request], interval_range: Tuple[int, int], batch_range: Tuple[int, int])))`:
    - This function performs operations similar to `send_batch_interval()`. However, the batch size is dynamically generated by a random number. Thus, the size of each batch can change. It also gathers all responses in the end, not per batch.