"""管理 PostgreSQL checkpoint 和 MCP 连接的生命周期。"""
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone
import logging
from typing import AsyncIterator
from urllib.parse import urlencode

import httpx2
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import URL, select

from app.core.config import DbSettings, RagSettings
from app.modules.conversation.models import ChatSession

logger = logging.getLogger(__name__)
WEB_SEARCH_MCP_URL = "https://open.bigmodel.cn/api/mcp/web_search/sse"


def create_mcp_http_client(headers=None, timeout=None, auth=None):
    """SSE 空闲时可以持续等待；MCP 请求另由 Client 的 60 秒超时约束。"""
    client_timeout = httpx2.Timeout(timeout if timeout is not None else 30)
    client_timeout.read = None
    return httpx2.AsyncClient(
        headers=headers, auth=auth,
        timeout=client_timeout,
    )


def _connection_uri(settings: DbSettings) -> str:
    """由 SQLAlchemy 转义用户名和密码，再交给 psycopg 连接 PostgreSQL。"""
    return URL.create(
        "postgresql",
        username=settings.user,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.name,
    ).render_as_string(hide_password=False)


@asynccontextmanager
async def conversation_lifespan(
    app, settings: DbSettings, rag_settings: RagSettings
) -> AsyncIterator[object]:
    """持有 PostgreSQL checkpointer；启动时发现 MCP 工具，调用时再连接。"""
    async with AsyncExitStack() as stack:
        web_tools = []
        # 智谱的网页搜索端点使用旧版 SSE；复用已有 ZHIPU_API_KEY 认证。
        from fastmcp.client import Client
        from fastmcp.client.transports import SSETransport
        from langchain.mcp import MCPAdapter

        web_url = WEB_SEARCH_MCP_URL + "?" + urlencode({
            "Authorization": rag_settings.zhipu_api_key.get_secret_value()
        })
        try:
            web_client = Client(
                SSETransport(url=web_url, httpx_client_factory=create_mcp_http_client),
                mode="legacy", timeout=60, init_timeout=30,
            )
            # list_tools 自行连接并关闭；返回的工具会在每次调用时重新打开连接。
            adapter = MCPAdapter(web_client)
            web_tools = await adapter.list_tools()
        except Exception as exc:
            logger.warning("智谱网页搜索 MCP 工具加载失败：%s", type(exc).__name__)
        checkpointer = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(_connection_uri(settings))
        )
        await checkpointer.setup()
        app.state.conversation_checkpointer = checkpointer
        try:
            yield web_tools
        finally:
            del app.state.conversation_checkpointer


async def save_session(session, session_id: str, question: str) -> None:
    """首问建立会话标题，后续回答只更新排序时间。"""
    row = await session.get(ChatSession, session_id)
    if row is None:
        session.add(ChatSession(id=session_id, title=question.strip()[:18] or "新会话"))
    else:
        if row.title == "新会话":
            row.title = question.strip()[:18] or "新会话"
        row.updated_at = datetime.now(timezone.utc)
    await session.commit()


async def list_sessions(session) -> list[ChatSession]:
    rows = await session.scalars(select(ChatSession).order_by(ChatSession.updated_at.desc()))
    return list(rows)
