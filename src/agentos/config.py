import os
from dotenv import load_dotenv

load_dotenv("chat.env")

API_BASE = os.getenv("OPENAI_API_BASE")
API_KEY = os.getenv("OPENAI_API_KEY")
API_MODEL = os.getenv("OPENAI_API_MODEL")