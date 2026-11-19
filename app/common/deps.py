"""从 FastAPI 应用状态注入共享数据库资源。"""
from typing import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database


def get_database(request: Request) -> Database:
    """读取当前应用 lifespan 创建的数据库资源。"""
    return request.app.state.database


def get_milvus(request: Request):
    """从应用 lifespan 中取出共享的 Milvus 客户端。"""
    return request.app.state.milvus


def get_conversation_graph(request: Request):
    """读取应用 lifespan 创建的 PostgreSQL checkpoint 图。"""
    return request.app.state.conversation_graph


def get_conversation_checkpointer(request: Request):
    """删除会话时清理对应的 PostgreSQL checkpoint。"""
    return request.app.state.conversation_checkpointer


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """每个请求独立使用 session，成功提交、异常回滚，最后关闭。"""
    database = get_database(request)
    async with database.session_factory() as session:
        try:
            yield session
            # 请求正常结束才提交；接口异常或提交失败时回滚，退出上下文时关闭 session。
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
