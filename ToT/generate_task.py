import random
from task_descriptions import *

generation_prompt_template = \
'''{instructions}

Make a plan then generate the output. If given a Draft Plan, then refine the Draft Plan and then generate the output. Your output should be of the following format:

Plan:
Your plan here.

Output:
Your {output_name} here'''

class TaskDescription:
    GenerationPrompt: str
    EvaluationPrompt: str
    NRounds: int
    NGenerationSamples: int
    NVoters: int

    def __str__(self):
        return f"GenerationPrompt:\n{self.GenerationPrompt}\n\nEvaluationPrompt:\n{self.EvaluationPrompt}\n\nNRounds: {self.NRounds}, NGenerationSamples: {self.NGenerationSamples}, NVoters: {self.NVoters}"

def get_task_description(task_name):
    task_description = TaskDescription()

    if task_name == 'end_with_random_sentence' or task_name == 'start_with_random_sentence':
        all_sentences = open("data_100_random_text.txt").readlines()
        sentences = all_sentences[random.randint(0, len(all_sentences)-1)].strip()
        task_description.GenerationPrompt = generation_prompt_template.format(
            instructions = tasks[task_name]['instructions'].format(sentences=sentences),
            output_name = "passage"
        )

    elif task_name == 'code_generation':
        coding_tasks = open("coding_tasks.txt").readlines()
        task = coding_tasks[random.randint(0, len(coding_tasks)-1)].strip()
        task_description.GenerationPrompt = generation_prompt_template.format(
            instructions = tasks[task_name]['instructions'].format(task=task),
            output_name = "code"
        )

    else:
        raise ValueError(f"Task {task_name} not found.")
    
    task_description.EvaluationPrompt = tasks[task_name]['evaluation']
    task_description.NRounds = tasks[task_name]['n_rounds']
    task_description.NGenerationSamples = tasks[task_name]['n_generation_samples']
    task_description.NVoters = tasks[task_name]['n_voters']
    
    return task_description

if __name__ == "__main__":
    task_name = input("Task name: ")
    task_description = get_task_description(task_name)
    print(task_description)