# models/agent.py — Agent 数据模型
from pydantic import BaseModel


class Agent(BaseModel):
    name: str
    identity: str
    system_prompt: str
