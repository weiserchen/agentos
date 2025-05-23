from agentos.tasks.task_descriptions import default_tasks

generation_prompt_template = """{instructions}

Make a plan then generate the output. If given a Draft Plan, then refine the Draft Plan and then generate the output. Your output should be of the following format:

Plan:
Your plan here.

Output:
Your {output_name} here"""


def get_task_description(task_name: str, task_input: str) -> str:
    task_description = None

    if (
        task_name == "end_with_random_sentence"
        or task_name == "start_with_random_sentence"
    ):
        task_description = generation_prompt_template.format(
            instructions=default_tasks[task_name]["instructions"].format(
                sentences=task_input
            ),
            output_name="passage",
        )

    elif task_name == "code_generation":
        task_description = generation_prompt_template.format(
            instructions=default_tasks[task_name]["instructions"].format(
                task=task_input
            ),
            output_name="code",
        )

    else:
        raise ValueError(f"Task {task_name} not found.")

    return task_description
