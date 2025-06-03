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

async def gather_votes_naive(
    coro_factories: list[Callable[[], Awaitable[dict]]],
    outputs: list[str],
) -> list[int]:
    """
        Run all voters to completion
    """
    tasks = [asyncio.create_task(f()) for f in coro_factories]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    votes: list[int] = []
    for r in results:
        try:
            if isinstance(r, Exception):
                continue
            votes.append(get_vote(r["body"]["result"], outputs))
        except Exception:
            continue
    return votes

async def gather_votes_until_majority(
    coro_factories: list[Callable[[], Awaitable[dict]]],
    outputs: list[str],
    majority: int,
) -> list[int]:
    """
    Launch voter coroutines, return as soon as one choice has reached a majority. 
    Any still-running tasks are cancelled.
    """
    tasks: set[asyncio.Task] = {
        asyncio.create_task(f()) for f in coro_factories
    }

    vote_counts = [0] * len(outputs)
    votes = []

    while tasks:
        done, tasks = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )

        for t in done:
            try:
                result = t.result()
                v = get_vote(result["body"]["result"], outputs)
            except Exception:
                continue

            votes.append(v)
            vote_counts[v] += 1

            if vote_counts[v] >= majority:
                for p in tasks:
                    p.cancel()
                return votes

            # Another optimisation: if the *best* candidate can no longer
            # be beaten even if all remaining votes go elsewhere
            remaining = len(tasks)
            best = max(vote_counts)
            second_best = sorted(vote_counts)[-2] if len(outputs) > 1 else 0
            if best > second_best + remaining:
                for p in tasks:
                    p.cancel()
                return votes

    return votes

class SimpleTreeTaskExecutor:
    def __init__(
        self,
        logger: AsyncLogger,
        task_id: int,
        node: TaskNode,
        get_agents: Callable[[], Awaitable[Dict[str, AgentInfo]]],
        load_balancing: str = "random",
        voting_strategy: str = "naive"
    ):
        self.logger = logger
        self.task_id = task_id
        self.node = node
        self.get_agents = get_agents
        self.result = None
        self.failed = False
        self.load_balancing = load_balancing
        self.voting_strategy = voting_strategy

    async def _generate_samples(
        self,
        prompt: str,
        stop: str | None,
        n_samples: int,
        round_idx: int,
    ) -> list[str]:
        workers = pick_k_agents(await self.get_agents(), n_samples, self.load_balancing)

        factories = [
            lambda b={
                "task_id": self.task_id,
                "task_round": round_idx,
                "task_action": TaskAction.GENERATION,
                "task_description": prompt,
                "task_stop": stop,
            }, addr=w.addr: http_post(addr + "/agent/call", b)
            for w in workers
        ]

        results = await asyncio.gather(
            *(f() for f in factories), return_exceptions=True
        )

        outputs: list[str] = []
        for r in results:
            if isinstance(r, Exception) or not r.get("success"):
                self.failed = True
                self.result = f"Worker Failure: {r.get('body', {}).get('error', 'Unknown Error')}"
                return []
            outputs.append(r["body"]["result"])
        return outputs

    async def _gather_votes(
        self,
        vote_prompt: str,
        outputs: list[str],
        n_voters: int,
        round_idx: int,
    ) -> list[int]:
        voters = pick_k_agents(await self.get_agents(), n_voters, self.load_balancing)
        factories = [
            lambda b={
                "task_id": self.task_id,
                "task_round": round_idx,
                "task_action": TaskAction.VOTING,
                "task_description": vote_prompt,
                "task_stop": None,
            }, addr=v.addr: http_post(addr + "/agent/call", b)
            for v in voters
        ]

        if self.voting_strategy == "naive":
            return await gather_votes_naive(factories, outputs)
        elif self.voting_strategy == "early_majority":
            majority = n_voters // 2 + 1
            return await gather_votes_until_majority(factories, outputs, majority)
        else:
            raise ValueError(f"Unknown voting strategy: {self.voting_strategy}")

    async def start(self):
        gen_prompt_base = self.node.description
        vote_prompt_base = self.node.evaluation
        n_rounds, n_samples, n_voters = (
            self.node.n_rounds,
            self.node.n_samples,
            self.node.n_voters,
        )

        draft_plan: str | None = None

        for r in range(n_rounds):
            await self.logger.info(f"[Round {r}] start")

            stop_token = None if r == n_rounds - 1 else "\nOutput:\n"
            gen_prompt = (
                f"{gen_prompt_base}\nGiven Hints: {draft_plan}"
                if draft_plan
                else gen_prompt_base
            )

            outputs = await self._generate_samples(gen_prompt, stop_token, n_samples, r)
            if self.failed:
                return
            await self.logger.info(f"[Round {r}] {len(outputs)} samples generated")

            vote_prompt = wrap_vote_prompt(outputs, vote_prompt_base)
            votes = await self._gather_votes(vote_prompt, outputs, n_voters, r)
            chosen_output = get_most_voted_output(votes, outputs)
            await self.logger.info(f"[Round {r}] voting finished")

            if r == n_rounds - 1:
                lower_output = chosen_output.lower()
                if "output:" in lower_output:
                    idx = lower_output.find("output:")
                    self.result = chosen_output[idx + len("output:") :].strip()
                    return
                else:
                    # self.failed = True
                    # self.result = f"Invalid output:\n{chosen_output}"
                    # return
                    self.result = chosen_output.strip() # Not catastrophic to return the whole output
                    return

            lower_output = chosen_output.lower()
            if "plan:" in lower_output:
                idx = lower_output.find("plan:")
                draft_plan = chosen_output[idx + len("plan:") :].strip()
            elif "plan" in lower_output[:20]:
                idx = lower_output[:20].find("plan")
                draft_plan = chosen_output[idx + len("plan") :].strip()
            else:
                self.failed = True
                self.result = f"Invalid plan:\n{chosen_output}"
                return