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


def pick_k_agents(agents: Dict[str, AgentInfo], k: int, load_balancing: str = "random") -> List[AgentInfo]:
    if load_balancing == "random":
        return pick_random_k_agents(agents, k)
    elif load_balancing == "least_loaded":
        return pick_least_loaded_k_agents(agents, k)
    else:
        raise ValueError(f"Unknown load balancing strategy: {load_balancing}")

def pick_random_k_agents(agents: Dict[str, AgentInfo], k: int) -> List[AgentInfo]:
    agent_list = list(agents.values())
    return random.choices(agent_list, k=k)

# def pick_least_loaded_k_agents(agents: Dict[str, AgentInfo], k: int) -> List[AgentInfo]:
#     counter = itertools.count()
#     heap = [
#         (a.workload, next(counter), aid) for aid, a in agents.items()
#     ]
#     heapq.heapify(heap)

#     chosen: List[AgentInfo] = []
#     for _ in range(k):
#         load, _, aid = heapq.heappop(heap)
#         chosen.append(agents[aid])
#         heapq.heappush(heap, (load + 1, next(counter), aid))

#     return chosen

def pick_least_loaded_k_agents(agents: Dict[str, AgentInfo], k: int) -> List[AgentInfo]:
    load = {aid: a.workload for aid, a in agents.items()}
    chosen: List[AgentInfo] = []

    for _ in range(k):
        best_id = min(load, key=load.get)
        chosen.append(agents[best_id])
        load[best_id] += 1

    return chosen


def filter_failed_responses(outputs: List[Any]) -> List[Any]:
    return list(filter(lambda x: x["success"], outputs))


def wrap_vote_prompt(choices, vote_prompt):
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
        round: int,
        result: str,
        node: TaskNode,
        get_agents: Callable[[], Awaitable[Dict[str, AgentInfo]]],
        load_balancing: str = "random",
    ):
        self.logger = logger
        self.task_id = task_id
        self.round = round
        self.node = node
        self.get_agents = get_agents
        self.result = result
        self.completed = False
        self.failed = False
        self.load_balancing = load_balancing

    async def run(self):
        generation_prompt = self.node.description
        vote_prompt = self.node.evaluation
        n_rounds = self.node.n_rounds
        n_samples = self.node.n_samples
        n_voters = self.node.n_voters

        if self.round == 0:
            draft_plan = None
        else:
            draft_plan = self.result

        while self.round < n_rounds:
            if self.round == n_rounds - 1:
                stop = None
            else:
                stop = "\nOutput:\n"

            await self.logger.info(f"[Round {self.round}] starting...")

            current_passage_generation_prompt = generation_prompt
            if draft_plan is not None:
                current_passage_generation_prompt = (
                    f"{generation_prompt}\nDraft Plan: {draft_plan}"
                )

<<<<<<< HEAD
            await self.logger.info(f"[Round {self.round}] generating samples...")
            workers: List[AgentInfo] = pick_random_k_agents(
=======
            await self.logger.info(f"[Round {round}] generating samples...")
            workers: List[AgentInfo] = pick_k_agents(
>>>>>>> e9aecc8 (Added Load Balancing)
                await self.get_agents(),
                n_samples,
                self.load_balancing,
            )
            futures = []
            for worker in workers:
                body = {
                    "task_id": self.task_id,
                    "task_round": self.round,
                    "task_action": TaskAction.GENERATION,
                    "task_description": current_passage_generation_prompt,
                    "task_stop": stop,
                }
                futures.append(
                    http_post(
                        self.logger,
                        worker.addr + "/agent/call",
                        body,
                    )
                )

            output_results = await asyncio.gather(*futures)
            await self.logger.info(f"[Round {self.round}] samples generated...")

            outputs = []
            # remove failed workers
            for i, result in enumerate(output_results):
                if result["success"]:
                    outputs.append(result["body"]["result"])
                else:
                    await self.logger.warning(
                        f"worker {workers[i].id} - request failed"
                    )

<<<<<<< HEAD
            await self.logger.info(f"[Round {self.round}] voting started...")
            vote_prompt = wrap_vote_prompts(outputs, vote_prompt)
            voters = pick_random_k_agents(await self.get_agents(), n_voters)
=======
            # TODO: remove failed workers

            await self.logger.info(f"[Round {round}] voting started...")
            vote_prompt = wrap_vote_prompt(outputs, vote_prompt)
            voters = pick_k_agents(await self.get_agents(), n_voters, self.load_balancing)
>>>>>>> e9aecc8 (Added Load Balancing)
            futures = []
            for voter in voters:
                body = {
                    "task_id": self.task_id,
                    "task_round": self.round,
                    "task_action": TaskAction.VOTING,
                    "task_description": vote_prompt,
                    "task_stop": None,
                }
                futures.append(
                    http_post(
                        self.logger,
                        voter.addr + "/agent/call",
                        body,
                    )
                )

            raw_vote_results = await asyncio.gather(*futures)
            raw_votes = []
            # remove failed voters
            for i, result in enumerate(raw_vote_results):
                if result["success"]:
                    raw_votes.append(result["body"]["result"])
                else:
                    await self.logger.warning(f"voter {voters[i].id} - request failed")

            votes = [get_vote(raw_vote, outputs) for raw_vote in raw_votes]
            chosen_output = get_most_voted_output(votes, outputs)
            await self.logger.info(f"[Round {self.round}] voting completed...")

            if self.round == n_rounds - 1:
                await self.logger.info(f"[Task {self.task_id}] task completed.")
                lower_output = chosen_output.lower()
                self.completed = True
                if "output:" in lower_output:
                    idx = lower_output.find("output:")
                    self.result = chosen_output[idx + len("output:\n") :].strip()
                else:
                    self.failed = True
                    self.result = f"Invalid output:\n{chosen_output}"

                yield
                return

            else:
                lower_output = chosen_output.lower()
                if "plan:" in lower_output:
                    idx = lower_output.find("output:")
                    draft_plan = chosen_output[idx + len("output:\n") :].strip()
                    self.result = draft_plan
                    yield
                    self.round += 1
                else:
                    self.failed = True
                    self.result = f"Invalid output:\n{chosen_output}"
                    self.completed = True
                    yield
                    return
