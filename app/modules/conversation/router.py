"""会话列表、历史与删除接口。"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_conversation_checkpointer, get_conversation_graph, get_session
from app.common.utils import ok
from app.modules.conversation.models import ChatSession
from app.modules.conversation.service import list_sessions

router = APIRouter(prefix="/api/sessions")


def _item(row: ChatSession) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "createdAt": int(row.created_at.timestamp() * 1000),
        "updatedAt": int(row.updated_at.timestamp() * 1000),
    }


@router.post("")
async def create_session(session: AsyncSession = Depends(get_session)):
    row = ChatSession(id=uuid.uuid4().hex, title="新会话")
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ok(_item(row))


@router.get("")
async def get_sessions(session: AsyncSession = Depends(get_session)):
    rows = await list_sessions(session)
    return ok([_item(row) for row in rows])


@router.get("/{session_id}")
async def get_session_history(
    session_id: str,
    session: AsyncSession = Depends(get_session),
    graph=Depends(get_conversation_graph),
):
    row = await session.get(ChatSession, session_id)
    if row is None:
        raise HTTPException(404, "会话不存在")
    snapshot = await graph.aget_state({"configurable": {"thread_id": session_id}})
    messages = snapshot.values.get("messages", []) if snapshot else []
    return ok({
        **_item(row),
        "messages": [
            {"id": message.id, "role": "user" if message.type == "human" else "assistant", "content": message.text,
             **({"sources": message.additional_kwargs.get("sources", [])} if message.type == "ai" else {})}
            for message in messages if message.type in {"human", "ai"}
        ],
    })


@router.delete("/{session_id}")
async def remove_session(
    session_id: str,
    session: AsyncSession = Depends(get_session),
    checkpointer=Depends(get_conversation_checkpointer),
):
    row = await session.get(ChatSession, session_id)
    if row is None:
        raise HTTPException(404, "会话不存在")
    await checkpointer.adelete_thread(session_id)
    await session.delete(row)
    await session.commit()
    return ok(message="删除成功")
