from .elem import TaskNode, TaskEvent, AgentCallTaskEvent
from .utils import http_post
from typing import Dict, List, Any
from pydantic import BaseModel
from fastapi import Query
from openai import AsyncOpenAI
from dotenv import load_dotenv
import random
import asyncio
import re
import os

class AgentInfo(BaseModel):
    id: str
    addr: str
    workload: int

def pick_agents(agents: List[AgentInfo], k: int) -> List[int]:
    if len(agents) <= 0:
        return []
    
    if len(agents) <= k:
        return [i for i in range(len(agents))]

    workload_sum = 0
    for agent in agents:
        workload_sum += (100 - agent.workload)

    picked_idx = []
    for i, agent in enumerate(agents):
        pick_prob = (100 - agent.workload) * k / workload_sum
        if random.random() < pick_prob:
            picked_idx.append(i)
            if len(picked_idx) >= k:
                return picked_idx
            
    # pad list to k
    for i, agent in enumerate(agents):
        if i not in picked_idx:
            picked_idx.append(i)
            if len(picked_idx) >= k:
                return picked_idx
            
def pick_agents_first_k(agents: Dict[str, AgentInfo], k: int) -> List[AgentInfo]:
    count = 0
    agent_infos = []
    for id, agent_info in agents.items():
        if count >= k:
            break
        agent_infos.append(agent_info)
        count += 1

    return agent_infos


def filter_failed_responses(outputs: List[Any]) -> List[Any]:
    return list(filter(lambda x: x['success'], outputs))

def wrap_vote_prompts(choices, vote_prompt):
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

class SimpleTreeTaskExecutor:
    def __init__(self, task_id: int, node: TaskNode, get_agents):
        self.task_id = task_id
        self.node = node
        # get the latest list of the agents
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
                stop = '\nOutput:\n'

            print(f'Starting round {round}...')

            current_passage_generation_prompt = generation_prompt
            if draft_plan is not None:
                current_passage_generation_prompt = f'{generation_prompt}\nDraft Plan: {draft_plan}'

            print('Generating samples...')
            agents: Dict[str, AgentInfo] = self.get_agents()
            # workers_idx = pick_agents(agents, n_samples)
            # workers_idx = [i for i in range(n_samples)]
            workers: List[AgentInfo] = pick_agents_first_k(agents, n_samples)
            futures = []
            for worker in workers:
                body = {
                    "task_description": current_passage_generation_prompt,
                    "task_stop": stop,
                }
                # print(f'original prompt: {generation_prompt}')
                # print(f'desc: {current_passage_generation_prompt}')
                # print(f'worker addr: {worker.addr+"/agent/call"}')
                futures.append(http_post(worker.addr+"/agent/call", body))

            output_results = await asyncio.gather(*futures)
            print(f'Samples generated...')
            outputs = []
            for result in output_results:
                if not result['success']:
                    self.failed = True
                    self.result = 'Worker Failure'
                    return
                outputs.append(result['body']['result'])

            # TODO: remove failed workers

            print(f'Voting started...')
            vote_prompt = wrap_vote_prompts(outputs, vote_prompt)
            # voters_idx = pick_agents(agents, n_voters)
            voters = pick_agents_first_k(agents, n_voters)
            futures = []
            for voter in voters:
                body = {
                    "task_description": vote_prompt,
                    "task_stop": None,
                }
                futures.append(http_post(voter.addr+"/agent/call", body))

            # TODO: remove failed voters

            raw_vote_results = await asyncio.gather(*futures)
            raw_votes = []
            for result in raw_vote_results:
                if not result['success']:
                    self.failed = True
                    self.result = 'Voter Failure'
                    return
                raw_votes.append(result['body']['result'])
                
            votes = [ get_vote(raw_vote)  for raw_vote in raw_votes]
            chosen_output = get_most_voted_output(votes, outputs)
            print(f'Voting completed...')

            if round == n_rounds - 1:
                print('Executor completed.')
                if "Output:" in chosen_output:
                    self.result = chosen_output.split('Output:\n')[-1]
                    return
                else:
                    self.failed = True
                    self.result = f'Invalid output:\n{chosen_output}'
                    return
            else:
                if chosen_output.startswith("Plan:"):
                    draft_plan = chosen_output[len('Plan:'):].strip()
                else:
                    self.failed = True
                    self.result = f'Invalid output:\n{chosen_output}'
                    return
            
