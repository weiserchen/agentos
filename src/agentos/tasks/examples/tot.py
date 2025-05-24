import asyncio
import os
import random
import re

from dotenv import load_dotenv
from openai import AsyncOpenAI

generation_prompt_template = """{instructions}

Make a plan then generate the output. If given a Draft Plan, then refine the Draft Plan and then generate the output. Your output should be of the following format:

Plan:
Your plan here.

Output:
Your {output_name} here"""

passage_generation_instuction_template = """I will provide you with four sentences. Your task is to write a coherent passage of four short paragraphs, each paragraph ending with one of my given sentences in the provided order. The four sentences are: {sentences}"""

vote_prompt = """Given an instruction and several choices, decide which choice is most promising. Analyze each choice in detail, then conclude in the LAST LINE WITH THIS EXACT PATTERN "The best choice is {s}", where s is the integer id of the choice."""

random.seed(43)
load_dotenv("chat.env")
api_base = os.getenv("OPENAI_API_BASE")
api_key = os.getenv("OPENAI_API_KEY")
api_model = os.getenv("OPENAI_API_MODEL")

all_sentences = open("./data_100_random_text.txt").readlines()
# sentences = all_sentences[random.randint(0, len(all_sentences)-1)].strip()
sentences = all_sentences[0].strip()
generation_prompt = generation_prompt_template.format(
    instructions=passage_generation_instuction_template.format(sentences=sentences),
    output_name="passage",
)


async def send_llm_request(prompt, model, stop) -> list:
    client = AsyncOpenAI(
        # base_url=api_base,
        api_key=api_key,
    )
    res = await client.chat.completions.create(
        model=api_model,
        temperature=0.7,
        max_tokens=2000,
        stop=stop,
        messages=[{"role": "user", "content": prompt}],
    )
    # print(res)
    content = res.choices[0].message.content
    print(content + "\n==================================\n")
    return content


def vote_prompt_wrap(choices):
    prompt = vote_prompt
    for idx, choice in enumerate(choices, 1):
        prompt += f"Choice {idx}:\n{choice}\n"
    return prompt


def get_vote(voter_output):
    pattern = r".*best choice is .*(\d+).*"
    match = re.match(pattern, voter_output, re.DOTALL)
    if match:
        return int(match.groups()[0]) - 1
    else:
        raise Exception("Invalid voter output: {voter_output}")


def get_most_voted_output(votes, outputs):
    # print(f'votes = {votes}\n')
    # print(f'outputs = {outputs}\n')
    vote_counts = [0] * len(outputs)
    for vote in votes:
        v = get_vote(vote)
        vote_counts[v] += 1
    most_voted_idx = vote_counts.index(max(vote_counts))
    return outputs[most_voted_idx]


async def tree():
    naive_generation_output = await send_llm_request(generation_prompt, api_model, None)

    n_rounds = 2
    n_generation_samples = 5
    n_voters = 5

    draft_plan = None
    tot_generation_output = None
    for n_round in range(n_rounds):
        if n_round == n_rounds - 1:
            stop = None
        else:
            stop = "\nOutput:\n"

        if draft_plan is not None:
            current_passage_generation_prompt = (
                f"{generation_prompt}\nDraft Plan: {draft_plan}"
            )
        else:
            current_passage_generation_prompt = generation_prompt

        outputs = []
        futures = [
            send_llm_request(current_passage_generation_prompt, api_model, stop)
            for _ in range(n_generation_samples)
        ]
        outputs = await asyncio.gather(*futures)

        print("==================================")
        print("Start voting...")
        print("==================================")

        vote_prompt = vote_prompt_wrap(outputs)
        votes = []
        futures = [
            send_llm_request(vote_prompt, api_model, None) for _ in range(n_voters)
        ]
        votes = await asyncio.gather(*futures)

        chosen_output = get_most_voted_output(votes, outputs)

        if n_round == n_rounds - 1:
            assert "Output:" in chosen_output
            tot_generation_output = chosen_output.split("Output:\n")[-1]
        else:
            assert chosen_output.startswith("Plan:")
            draft_plan = chosen_output[len("Plan:") :].strip()

    output = """
Sentences:
{sentences}
----------------------------------------------------------------------------------------------------------------
Prompt:
{prompt}
----------------------------------------------------------------------------------------------------------------
Naive Generation:
{naive_generation_output}
----------------------------------------------------------------------------------------------------------------
ToT Generation:
{tot_generation_output}
    """.format(
        sentences="\n".join(
            f"* {s.strip()}" for s in sentences.split(".") if s.strip()
        ),
        prompt=generation_prompt,
        naive_generation_output=naive_generation_output,
        tot_generation_output=tot_generation_output,
    )

    print(output)


if __name__ == "__main__":
    asyncio.run(tree())
    # asyncio.run(naive())
