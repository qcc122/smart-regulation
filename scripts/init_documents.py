"""把指定本地目录中的 PDF/DOCX 导入 RAG 知识库。"""
import argparse
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import get_settings
from app.core.database import create_database, initialize_schema
from app.modules.document.service import ingest_document
from app.core.logging import configure_logging
from app.modules.agent.repository import milvus_lifespan

logger = logging.getLogger(__name__)
_SUPPORTED_SUFFIXES = {".pdf", ".docx"}


def find_documents(directory: str | Path) -> list[Path]:
    """递归查找 PDF/DOCX；其它扩展名不进入 ingestion pipeline。"""
    root = Path(directory).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(f"资料夹不存在：{root}")
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )


async def ingest_files(files: list[Path], session_factory, milvus) -> dict[str, int]:
    """逐份调用与上传 API 相同的 pipeline；单个文件失败时继续处理。"""
    summary = {"added": 0, "skipped": 0, "failed": 0}
    for path in files:
        try:
            async with session_factory() as session:
                try:
                    result = await ingest_document(
                        session,
                        milvus,
                        path,
                        uuid4().hex[:12],
                        path.name,
                    )
                except Exception:
                    await session.rollback()
                    raise
            status = "added" if result.created else "skipped"
            summary[status] += 1
            logger.info("本地文档%s file=%s doc_id=%s", "已入库" if result.created else "已存在", path.name, result.doc_id)
        except Exception as exc:
            summary["failed"] += 1
            logger.error("本地文档入库失败 file=%s error_type=%s", path.name, type(exc).__name__)
    return summary


async def ingest_directory(directory: str | Path, session_factory, milvus) -> dict[str, int]:
    """扫描目录并按同一 pipeline 逐份导入。"""
    return await ingest_files(find_documents(directory), session_factory, milvus)


async def initialize_directory(directory: str | Path) -> dict[str, int]:
    """连接项目数据库和 Milvus，并在关闭时释放两类资源。"""
    files = find_documents(directory)
    if not files:
        return {"added": 0, "skipped": 0, "failed": 0}

    settings = get_settings()
    settings.validate_required()
    configure_logging(secrets=[
        secret.get_secret_value()
        for secret in (settings.zhipu_api_key, settings.postgres_password, settings.mineru_token)
        if secret is not None
    ])

    database = create_database(settings.db)
    app = SimpleNamespace(state=SimpleNamespace())
    try:
        await initialize_schema(database.engine)
        async with milvus_lifespan(
            app,
            settings.rag.milvus_uri,
            settings.rag.milvus_db_name,
            settings.rag.milvus_collection_name,
            settings.rag.vector_dim,
        ) as milvus:
            return await ingest_files(files, database.session_factory, milvus)
    finally:
        await database.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化本地法规 PDF/DOCX 文档")
    parser.add_argument("directory", type=Path, help="待导入的文档目录，递归扫描 PDF/DOCX")
    args = parser.parse_args()
    try:
        summary = asyncio.run(initialize_directory(args.directory))
    except NotADirectoryError as exc:
        parser.error(str(exc))
    except Exception as exc:
        print(f"初始化失败：{type(exc).__name__}")
        return 1

    print(
        "初始化完成：新增 {added}，已存在 {skipped}，失败 {failed}。".format(**summary)
    )
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
