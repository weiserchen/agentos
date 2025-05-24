import os

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "chat.env")
load_dotenv(env_path)

API_BASE = os.getenv("OPENAI_API_BASE")
API_KEY = os.getenv("OPENAI_API_KEY")
API_MODEL = os.getenv("OPENAI_API_MODEL")
