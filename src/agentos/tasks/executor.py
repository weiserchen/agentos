import asyncio
import random
import re
from typing import Any, Dict, List

from pydantic import BaseModel

from agentos.tasks.elem import TaskNode
from agentos.tasks.utils import http_post
from agentos.utils.logger import AsyncLogger


class AgentInfo(BaseModel):
    id: str
    addr: str
    workload: int


def pick_random_k_agents(agents: Dict[str, AgentInfo], k: int) -> List[AgentInfo]:
    agent_list = list(agents.values())
    return random.choices(agent_list, k=k)


def filter_failed_responses(outputs: List[Any]) -> List[Any]:
    return list(filter(lambda x: x["success"], outputs))


def wrap_vote_prompts(choices, vote_prompt):
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
    vote_counts = [0] * len(outputs)
    for v in votes:
        vote_counts[v] += 1
    most_voted_idx = vote_counts.index(max(vote_counts))
    return outputs[most_voted_idx]


class SimpleTreeTaskExecutor:
    def __init__(
        self,
        logger: AsyncLogger,
        task_id: int,
        node: TaskNode,
        agents: Dict[str, AgentInfo],
    ):
        self.logger = logger
        self.task_id = task_id
        self.node = node
        self.agents = agents
        self.result = None
        self.done = False
        self.failed = False

    async def start(self):
        generation_prompt = self.node.description
        vote_prompt = self.node.evaluation
        n_rounds = self.node.n_rounds
        n_samples = self.node.n_samples
        n_voters = self.node.n_voters

        draft_plan = None
        for round in range(n_rounds):
            if round == n_rounds - 1:
                stop = None
            else:
                stop = "\nOutput:\n"

            await self.logger.info(f"Starting round {round}...")

            current_passage_generation_prompt = generation_prompt
            if draft_plan is not None:
                current_passage_generation_prompt = (
                    f"{generation_prompt}\nDraft Plan: {draft_plan}"
                )

            await self.logger.info("Generating samples...")
            workers: List[AgentInfo] = pick_random_k_agents(self.agents, n_samples)
            futures = []
            for worker in workers:
                body = {
                    "task_description": current_passage_generation_prompt,
                    "task_stop": stop,
                }
                futures.append(http_post(worker.addr + "/agent/call", body))

            output_results = await asyncio.gather(*futures)
            await self.logger.info("Samples generated...")
            outputs = []
            for result in output_results:
                if not result["success"]:
                    self.failed = True
                    self.result = "Worker Failure"
                    return
                outputs.append(result["body"]["result"])

            # TODO: remove failed workers

            await self.logger.info("Voting started...")
            vote_prompt = wrap_vote_prompts(outputs, vote_prompt)
            voters = pick_random_k_agents(self.agents, n_voters)
            futures = []
            for voter in voters:
                body = {
                    "task_description": vote_prompt,
                    "task_stop": None,
                }
                futures.append(http_post(voter.addr + "/agent/call", body))

            # TODO: remove failed voters

            raw_vote_results = await asyncio.gather(*futures)
            raw_votes = []
            for result in raw_vote_results:
                if not result["success"]:
                    self.failed = True
                    self.result = "Voter Failure"
                    return
                raw_votes.append(result["body"]["result"])

            votes = [get_vote(raw_vote) for raw_vote in raw_votes]
            chosen_output = get_most_voted_output(votes, outputs)
            await self.logger.info("Voting completed...")

            if round == n_rounds - 1:
                await self.logger.info("Executor completed.")
                if "Output:" in chosen_output:
                    self.result = chosen_output.split("Output:\n")[-1]
                    return
                else:
                    self.failed = True
                    self.result = f"Invalid output:\n{chosen_output}"
                    return
            else:
                if chosen_output.startswith("Plan:"):
                    draft_plan = chosen_output[len("Plan:") :].strip()
                else:
                    self.failed = True
                    self.result = f"Invalid output:\n{chosen_output}"
                    return
