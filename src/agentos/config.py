import os

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "chat.env")
load_dotenv(env_path)

run_local = True

API_BASE = os.getenv("OPENAI_API_BASE")
API_KEY = os.getenv("OPENAI_API_KEY")
API_MODEL = os.getenv("OPENAI_API_MODEL")

LOCAL_API_BASE='http://127.0.0.1:{port}/v1'
LOCAL_API_KEY='EMPTY'
# LOCAL_MODEL='mistralai/Mixtral-8x7B-Instruct-v0.1'
LOCAL_MODEL='meta-llama/Llama-3.1-8B-Instruct'