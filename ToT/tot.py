import re
from generate_task import TaskDescription
from concurrent.futures import ThreadPoolExecutor, as_completed

def vote_prompt_wrap(choices, vote_prompt):
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

def tot(task_description: TaskDescription, thread_pool: ThreadPoolExecutor, send_llm_request):
    generation_prompt = task_description.GenerationPrompt
    vote_prompt = task_description.EvaluationPrompt
    n_rounds = task_description.NRounds
    n_generation_samples = task_description.NGenerationSamples
    n_voters = task_description.NVoters

    draft_plan = None
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
        futures = [thread_pool.submit(send_llm_request, current_passage_generation_prompt, stop)
                for _ in range(n_generation_samples)]
        outputs = [f.result() for f in as_completed(futures)]

        vote_prompt = vote_prompt_wrap(outputs, vote_prompt)
        votes = []
        futures = [thread_pool.submit(send_llm_request, vote_prompt, None)
                for _ in range(n_voters)]
        votes = [get_vote(f.result()) for f in as_completed(futures)]

        chosen_output = get_most_voted_output(votes, outputs)

        if n_round == n_rounds - 1:
            assert "Output:" in chosen_output, f'Invalid output:\n{chosen_output}'
            return chosen_output.split('Output:\n')[-1]
        else:
            assert chosen_output.startswith("Plan:"), f'Invalid output:\n{chosen_output}'
            draft_plan = chosen_output[len('Plan:'):].strip()