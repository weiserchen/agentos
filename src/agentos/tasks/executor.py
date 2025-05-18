from .elem import TaskNode, TaskEvent
from .utils import fetch, fetch_all
from typing import Dict, List
import random

class SimpleTaskExecutor:
    def __init__(self, node: TaskNode, url_map: Dict[str, str]):
        self.node = node
        self.done = False
        self.req_error = False
        self.url_map = url_map
        self.response = None

    async def start(self):
        # TODO: use true request
        url = self.url_map[self.node.agent]
        result = await fetch(url)
        if result['status'] > 200:
            self.req_error = True
        else:
            self.response = result['body']
            self.done = True

class SimpleTreeTaskExecutor:
    def __init__(self, node: TaskNode, urls: List[str], max_depth: int = 2, max_breadth: int = 5, max_voter: int = 3):
        self.node = node
        self.urls = urls
        self.url_idx = 0
        self.max_depth = max_depth
        self.max_breadth = max_breadth
        self.max_voter = max_voter
        self.history = [node.description]
        self.level_rankings = []
        self.done = False

    async def start(self):
        # TODO: use real requests
        urls = list(self.url_map.values())
        for _ in range(self.max_depth):
            workers = random.sample(urls)
            voters = random.sample(urls)
            results = await fetch_all(workers)
            # TODO: add results in the request
            rankings = await fetch_all(voters)
            merged_ranking = []
            
            
            # TODO: merge rankings
            self.level_rankings.append(results_ranking)
