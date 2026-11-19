"""聊天路由：同步调用主图，流式请求交给 service。"""
import uuid
from contextlib import aclosing

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse

from app.common.deps import get_conversation_graph, get_database
from app.common.utils import ok
from app.modules.chat.schemas import ChatRequest
from app.modules.chat.service import _config, _input, stream_chat
from app.modules.conversation.service import save_session

router = APIRouter(prefix="/api/chat")
stream_router = APIRouter(prefix="/stream")


@router.post("")
async def chat(req: ChatRequest, graph=Depends(get_conversation_graph), db=Depends(get_database)):
    """意图路由、工具调用和回答校验都在同一次图执行中完成。"""
    session_id = req.session_id or uuid.uuid4().hex[:12]
    result = await graph.ainvoke(_input(req), _config(session_id))
    async with db.session_factory() as session:
        await save_session(session, session_id, req.question)
    return ok({"session_id": session_id, "answer": result["answer"], "sources": result.get("sources", [])})


@stream_router.post("", response_class=EventSourceResponse)
async def chat_stream(req: ChatRequest, graph=Depends(get_conversation_graph), db=Depends(get_database)):
    """FastAPI 负责 SSE 编码、心跳和断连取消。"""
    async with aclosing(stream_chat(req, graph, db)) as stream:
        async for event in stream:
            yield event


router.include_router(stream_router)
