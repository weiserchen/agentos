import asyncio
import random
import re
from typing import Any, Awaitable, Callable, Dict, List

from pydantic import BaseModel

from agentos.tasks.elem import TaskAction, TaskNode
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


def get_vote(voter_output, outputs):
    pattern = r".*best choice is .*(\d+).*"
    match = re.match(pattern, voter_output, re.IGNORECASE | re.DOTALL)
    if match:
        return int(match.groups()[0]) - 1
    else:
        # raise Exception("Invalid voter output: {voter_output}")
        return random.randint(0, len(outputs) - 1)


def get_most_voted_output(votes, outputs):
    vote_counts = [0] * len(outputs)
    for v in votes:
        if 0 <= v < len(outputs):
            vote_counts[v] += 1
        else:
            random_idx = random.randint(0, len(outputs) - 1)
            vote_counts[random_idx] += 1
    most_voted_idx = vote_counts.index(max(vote_counts))
    return outputs[most_voted_idx]


class SimpleTreeTaskExecutor:
    def __init__(
        self,
        logger: AsyncLogger,
        task_id: int,
        node: TaskNode,
        get_agents: Callable[[], Awaitable[Dict[str, AgentInfo]]],
    ):
        self.logger = logger
        self.task_id = task_id
        self.node = node
        self.get_agents = get_agents
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

            await self.logger.info(f"[Round {round}] starting...")

            current_passage_generation_prompt = generation_prompt
            if draft_plan is not None:
                current_passage_generation_prompt = (
                    f"{generation_prompt}\nDraft Plan: {draft_plan}"
                )

            await self.logger.info(f"[Round {round}] generating samples...")
            workers: List[AgentInfo] = pick_random_k_agents(
                await self.get_agents(),
                n_samples,
            )
            futures = []
            for worker in workers:
                body = {
                    "task_id": self.task_id,
                    "task_round": round,
                    "task_action": TaskAction.GENERATION,
                    "task_description": current_passage_generation_prompt,
                    "task_stop": stop,
                }
                futures.append(http_post(worker.addr + "/agent/call", body))

            output_results = await asyncio.gather(*futures)
            await self.logger.info(f"[Round {round}] samples generated...")
            outputs = []
            for result in output_results:
                if not result["success"]:
                    self.failed = True
                    self.result = "Worker Failure"
                    return
                outputs.append(result["body"]["result"])

            # TODO: remove failed workers

            await self.logger.info(f"[Round {round}] voting started...")
            vote_prompt = wrap_vote_prompts(outputs, vote_prompt)
            voters = pick_random_k_agents(await self.get_agents(), n_voters)
            futures = []
            for voter in voters:
                body = {
                    "task_id": self.task_id,
                    "task_round": round,
                    "task_action": TaskAction.VOTING,
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

            votes = [get_vote(raw_vote, outputs) for raw_vote in raw_votes]
            chosen_output = get_most_voted_output(votes, outputs)
            await self.logger.info(f"[Round {round}] voting completed...")

            if round == n_rounds - 1:
                await self.logger.info(f"[Task {self.task_id}] task completed.")
                lower_output = chosen_output.lower()
                if "output:" in lower_output:
                    idx = lower_output.find("output:")
                    self.result = chosen_output[idx + len("output:\n") :].strip()
                    return
                else:
                    self.failed = True
                    self.result = f"Invalid output:\n{chosen_output}"
                    return
            else:
                lower_output = chosen_output.lower()
                if "plan:" in lower_output:
                    idx = lower_output.find("output:")
                    draft_plan = chosen_output[idx + len("output:\n") :].strip()
                else:
                    self.failed = True
                    self.result = f"Invalid output:\n{chosen_output}"
                    return