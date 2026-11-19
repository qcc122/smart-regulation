"""FastAPI 入口：装配基础资源、异常处理与业务路由。"""
from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_session
from app.common.utils import ok
from app.core.config import get_settings
from app.core.database import database_lifespan
from app.core.logging import configure_logging
from app.modules.agent.repository import milvus_lifespan
from app.modules.agent.graph import build_graph
from app.modules.chat.router import router as chat_router
from app.modules.conversation.service import conversation_lifespan
from app.modules.conversation.router import router as conversation_router
from app.modules.document.router import router as document_router

logger = logging.getLogger("rag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时创建共享资源，应用退出时由各自的 lifespan 释放。"""
    settings = get_settings()
    configure_logging(secrets=[
        secret.get_secret_value()
        for secret in (
            settings.zhipu_api_key,
            settings.postgres_password,
            settings.siliconflow_api_key,
            settings.mineru_token,
        )
        if secret is not None
    ])
    settings.validate_required()
    # 数据库和 Milvus 只在服务运行期间共享；退出时按相反顺序释放。
    async with database_lifespan(app, settings.db):
        async with milvus_lifespan(
            app,
            settings.rag.milvus_uri,
            settings.rag.milvus_db_name,
            settings.rag.milvus_collection_name,
            settings.rag.vector_dim,
        ):
            async with conversation_lifespan(app, settings.db, settings.rag) as web_tools:
                # 启动时构建一次主图，请求只复用已绑定同一 checkpointer 的图。
                app.state.conversation_graph = build_graph(
                    app.state.conversation_checkpointer,
                    app.state.database.session_factory,
                    app.state.milvus,
                    settings.rag,
                    web_tools,
                )
                try:
                    logger.info("服务启动完成，Milvus 与 PostgreSQL 会话检查点已连接")
                    yield
                finally:
                    del app.state.conversation_graph

app = FastAPI(title="住建法规RAG问答系统", version="1.0.0", lifespan=lifespan)
app.include_router(document_router)
app.include_router(chat_router)
app.include_router(conversation_router)


@app.exception_handler(HTTPException)
async def http_exc_handler(request, exc):
    return JSONResponse(status_code=exc.status_code,
                        content={"code": exc.status_code, "message": exc.detail, "data": None})


@app.exception_handler(Exception)
async def generic_exc_handler(request, exc):
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content={"code": 500, "message": "服务器内部错误", "data": None})

@app.get("/api/health")
async def health(session: AsyncSession = Depends(get_session)):
    # readiness 同时确认数据库可查询，而不只确认 FastAPI 进程仍在运行。
    await session.execute(text("SELECT 1"))
    return ok({"status": "up"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
