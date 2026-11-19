"""聊天请求模型。"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1, max_length=64)
    top_k: int | None = None
