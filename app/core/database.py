"""PostgreSQL 异步引擎与 session 生命周期。"""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from fastapi import FastAPI
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import ConfigurationError, DbSettings


@dataclass
class Database:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


def create_database(settings: DbSettings) -> Database:
    if settings.password is None or not settings.password.get_secret_value().strip():
        raise ConfigurationError("Missing required settings: POSTGRES_PASSWORD")

    # URL.create 负责转义密码中的特殊字符；这里只创建引擎，不发起网络连接。
    url = URL.create(
        "postgresql+asyncpg",
        username=settings.user,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.name,
    )
    engine = create_async_engine(
        url,
        # 连接池按每个 API worker 计；部署时需将总连接数与 PostgreSQL 上限一起核算。
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
        pool_pre_ping=True,
    )
    return Database(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )


async def initialize_schema(engine: AsyncEngine) -> None:
    """幂等创建当前项目缺少的表；不删除或改写已有表和数据。"""
    from app.modules.conversation import models as conversation_models  # 注册会话表
    from app.modules.document.models import Base

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def database_lifespan(app: FastAPI, settings: DbSettings) -> AsyncIterator[Database]:
    database = create_database(settings)
    app.state.database = database
    try:
        await initialize_schema(database.engine)
        yield database
    finally:
        try:
            await database.engine.dispose()
        finally:
            # 即使释放连接时报错，也清掉 app.state 中已失效的资源引用。
            del app.state.database
