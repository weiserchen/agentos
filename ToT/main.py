import os
import openai
from dotenv import load_dotenv
from generate_task import get_task_description
from concurrent.futures import ThreadPoolExecutor, as_completed
from tot import tot
from task_descriptions import tasks

load_dotenv()
THREAD_POOL = ThreadPoolExecutor(max_workers=5)

openai.api_base = os.getenv("OPENAI_API_BASE")
openai.api_key = os.getenv("OPENAI_API_KEY")

def send_llm_request(prompt, stop) -> list:
    model = 'meta-llama/Llama-3.3-70B-Instruct'
    messages = [{"role": "user", "content": prompt}]
    kwargs = {
        "model": model, "messages": messages, "temperature": 0.7, "max_tokens": 2000, "stop":stop
    }
    res = openai.ChatCompletion.create(**kwargs)
    return res.choices[0].message.content

task_options = list(tasks.keys())
task_name = input(f"Task Options: {task_options}\nTask name: ")
task_description = get_task_description(task_name)

tot_generation = tot(task_description, THREAD_POOL, send_llm_request)

print(f'Prompt:\n{task_description.GenerationPrompt}')
print('-'*100)
print(f'Output:\n{tot_generation}')