"""清理本项目文档表、Milvus collection 和上传副本。"""
import argparse
import asyncio
from pathlib import Path
import re

from sqlalchemy import delete, text

from app.core.config import UPLOAD_DIR, get_settings
from app.core.database import create_database, initialize_schema
from app.modules.document.models import DocumentRecord, ParentChunk
from app.modules.agent.repository import create_milvus_store


def drop_milvus_collection(uri: str, db_name: str, collection_name: str, dim: int) -> bool:
    """通过 LangChain Milvus 只删除当前项目配置的 collection。"""
    store = create_milvus_store(uri, db_name, collection_name, dim)
    if store.col is None:
        return False
    store.drop()
    return True


async def reset_postgres_documents(settings) -> None:
    """只清空当前应用的父块和文档表，不删除数据库或其它表。"""
    database = create_database(settings.db)
    try:
        await initialize_schema(database.engine)
        await clear_postgres_documents(database)
    finally:
        await database.engine.dispose()


async def clear_postgres_documents(database) -> None:
    """删除两张项目文档表的记录。"""
    async with database.session_factory() as session:
        await session.execute(delete(ParentChunk))
        await session.execute(delete(DocumentRecord))
        await session.commit()


def clear_uploaded_copies(upload_dir: str | Path) -> int:
    """只删除 API 按 doc_id 前缀保存的上传副本。"""
    directory = Path(upload_dir)
    if not directory.is_dir():
        return 0

    generated_name = re.compile(r"^[a-f0-9]{12}_.+")
    removed = 0
    for path in directory.iterdir():
        if path.is_file() and generated_name.fullmatch(path.name):
            path.unlink()
            removed += 1
    return removed


async def reset_application_data(settings) -> tuple[bool, int]:
    """清理已配置的 RAG 数据，并保留基础数据库和 Milvus database。"""
    database = create_database(settings.db)
    try:
        await initialize_schema(database.engine)
        # 先确认 PostgreSQL 可用，避免数据库凭据/连接错误后只删掉 Milvus 数据。
        async with database.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        collection_removed = drop_milvus_collection(
            settings.milvus_uri,
            settings.milvus_db_name,
            settings.milvus_collection_name,
            settings.vector_dim,
        )
        await clear_postgres_documents(database)
        uploads_removed = clear_uploaded_copies(UPLOAD_DIR)
        return collection_removed, uploads_removed
    finally:
        await database.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="清空本项目的法规文档、向量和上传副本")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="确认删除配置的 RAG collection 和本项目文档记录",
    )
    args = parser.parse_args()
    settings = get_settings()

    print(f"PostgreSQL 文档表: {settings.postgres_db}.rag_documents / rag_parent_chunks")
    print(f"Milvus collection: {settings.milvus_db_name}.{settings.milvus_collection_name}")
    print(f"应用上传目录: {UPLOAD_DIR}")
    if not args.confirm:
        print("未执行。确认清理范围后，请重新运行并添加 --confirm。")
        return 2

    collection_removed, uploads_removed = asyncio.run(reset_application_data(settings))
    print(
        "清理完成：Milvus collection %s，上传副本 %d 个；PostgreSQL 文档表已清空。"
        % ("已删除" if collection_removed else "原本不存在", uploads_removed)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
