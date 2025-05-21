import os
import openai
from dotenv import load_dotenv
import random
from generate_task import get_task_description
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

random.seed(43)
load_dotenv()
THREAD_POOL = ThreadPoolExecutor(max_workers=5)

openai.api_base = os.getenv("OPENAI_API_BASE")
openai.api_key = os.getenv("OPENAI_API_KEY")

model = 'meta-llama/Llama-3.3-70B-Instruct'

def send_llm_request(prompt, model, stop) -> list:
    messages = [{"role": "user", "content": prompt}]
    kwargs = {
        "model": model, "messages": messages, "temperature": 0.7, "max_tokens": 2000, "stop":stop
    }
    res = openai.ChatCompletion.create(**kwargs)
    return res.choices[0].message.content


task_name = input("Task name: ")
task_description = get_task_description(task_name)

generation_prompt = task_description.GenerationPrompt
vote_prompt = task_description.EvaluationPrompt
n_rounds = task_description.NRounds
n_generation_samples = task_description.NGenerationSamples
n_voters = task_description.NVoters

naive_generation_output = send_llm_request(generation_prompt, model, None)

def vote_prompt_wrap(choices):
    prompt = vote_prompt
    for idx, choice in enumerate(choices, 1):
        prompt += f'Choice {idx}:\n{choice}\n'
    return prompt

def get_vote(voter_output):
    pattern = r".*best choice is .*(\d+).*"
    match = re.match(pattern, voter_output, re.DOTALL)
    if match:
        return int(match.groups()[0]) - 1
    else:
        raise Exception("Invalid voter output: {voter_output}".format(voter_output))

def get_most_voted_output(votes, outputs):
    vote_counts = [0] * len(outputs)
    for v in votes:
        vote_counts[v] += 1
    most_voted_idx = vote_counts.index(max(vote_counts))
    return outputs[most_voted_idx]

draft_plan = None
tot_generation_output = None
for n_round in range(n_rounds):

    if n_round == n_rounds - 1:
        stop = None
    else:
        stop = '\nOutput:\n'

    if draft_plan is not None:
        current_passage_generation_prompt = \
        f'{generation_prompt}\nDraft Plan: {draft_plan}'
    else:
        current_passage_generation_prompt = generation_prompt

    outputs = []
    futures = [THREAD_POOL.submit(send_llm_request, current_passage_generation_prompt, model, stop)
               for _ in range(n_generation_samples)]
    outputs = [f.result() for f in as_completed(futures)]

    vote_prompt = vote_prompt_wrap(outputs)
    votes = []
    futures = [THREAD_POOL.submit(send_llm_request, vote_prompt, model, None)
               for _ in range(n_voters)]
    votes = [get_vote(f.result()) for f in as_completed(futures)]
    print(votes, "\n")

    chosen_output = get_most_voted_output(votes, outputs)

    if n_round == n_rounds - 1:
        assert "Output:" in chosen_output, f'Invalid output:\n{chosen_output}'
        tot_generation_output = chosen_output.split('Output:\n')[-1]
    else:
        assert chosen_output.startswith("Plan:"), f'Invalid output:\n{chosen_output}'
        draft_plan = chosen_output[len('Plan:'):].strip()

output = \
'''
Prompt:
{prompt}
----------------------------------------------------------------------------------------------------------------
Naive Generation:
{naive_generation_output}
----------------------------------------------------------------------------------------------------------------
ToT Generation:
{tot_generation_output}
'''.format(
        prompt=generation_prompt,
        naive_generation_output=naive_generation_output,
        tot_generation_output=tot_generation_output
)

print(output)