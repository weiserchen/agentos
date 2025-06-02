from agentos.tasks.elem import TaskNode, CoordinatorTaskEvent
from agentos.tasks.task_descriptions import default_tasks

generation_prompt_template = """{instructions}

Make a plan then generate the output. If given hints, then use ideas from the hints to come with a plan and then generate the output.

Your output should be of the following format exactly:
"PLAN:
Your plan here.

OUTPUT:
Your {output_name} here"
"""


def get_task_description(task_name: str, task_description: str) -> str:
    if (
        task_name == "end_with_random_sentence"
        or task_name == "start_with_random_sentence"
    ):
        return generation_prompt_template.format(
            instructions=default_tasks[task_name]["instructions"].format(
                sentences=task_description
            ),
            output_name="passage",
        )

    elif task_name == "code_generation":
        return generation_prompt_template.format(
            instructions=default_tasks[task_name]["instructions"].format(
                task=task_description
            ),
            output_name="code",
        )

    else:
        raise ValueError(f"Task {task_name} not found.")


def get_task_node(task_event: CoordinatorTaskEvent) -> TaskNode:
    task = default_tasks[task_event.task_name]
    task_node = TaskNode(
        description=get_task_description(task_event.task_name, task_event.task_description),
        evaluation=task["evaluation"],
        n_rounds=task_event.n_rounds,
        n_samples=task_event.n_samples,
        n_voters=task_event.n_voters,
    )
    return task_node