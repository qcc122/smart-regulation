"""在 MinerU Markdown、PostgreSQL 父块和 Milvus 子向量之间协调入库。"""
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.modules.document.splitter import split_markdown
from app.modules.document.parser import DocumentParseError, parse_document
from app.modules.document.models import DocumentRecord, ParentChunk
from app.modules.agent.repository import add_document, delete_document as delete_vectors

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    doc_id: str
    source_file: str
    title: str
    parent_count: int
    chunk_count: int
    created: bool


async def ingest_document(
    session: AsyncSession,
    milvus,
    path: str | Path,
    doc_id: str,
    source_file: str,
) -> IngestionResult:
    """提取并切分文档，再写入向量库子块和数据库父块。"""
    path = Path(path)
    content_sha256 = await run_in_threadpool(lambda: hashlib.sha256(path.read_bytes()).hexdigest())
    existing = await session.scalar(
        select(DocumentRecord).where(DocumentRecord.content_sha256 == content_sha256)
    )
    if existing is not None and existing.status == "ready":
        return IngestionResult(
            doc_id=existing.doc_id,
            source_file=existing.source_file,
            title=existing.title,
            parent_count=existing.parent_count,
            chunk_count=existing.chunk_count,
            created=False,
        )

    # MinerU 网络请求和切分是同步库调用，放在线程池中避免阻塞 API event loop。
    markdown = await run_in_threadpool(parse_document, path, source_file)
    title = Path(source_file).stem
    parents, children = await run_in_threadpool(
        split_markdown,
        markdown,
        doc_id=doc_id,
        source_file=source_file,
        title=title,
    )
    if not parents or not children:
        raise DocumentParseError(f"文档没有可入库的 Markdown 内容：{source_file}")

    vectors_attempted = False
    try:
        # 先写子向量；若后续数据库提交失败，会按 doc_id 补偿删除。
        vectors_attempted = True
        await run_in_threadpool(add_document, milvus, doc_id, children)

        session.add(DocumentRecord(
            doc_id=doc_id,
            content_sha256=content_sha256,
            source_file=source_file,
            source_type=path.suffix.lower().lstrip("."),
            title=title,
            status="ready",
            parent_count=len(parents),
            chunk_count=len(children),
        ))
        session.add_all([
            ParentChunk(
                id=UUID(parent["parent_id"]),
                doc_id=doc_id,
                parent_index=parent["parent_index"],
                content=parent["content"],
                title=parent["title"],
                section_path=parent["section_path"],
                source_file=parent["source_file"],
            )
            for parent in parents
        ])
        await session.commit()
    except Exception:
        await session.rollback()
        if vectors_attempted:
            try:
                await run_in_threadpool(delete_vectors, milvus, doc_id)
            except Exception:
                # 补偿失败需保留日志，便于后续按 doc_id 清理孤立向量。
                logger.exception("文档入库补偿删除失败 doc_id=%s", doc_id)
        raise

    return IngestionResult(
        doc_id=doc_id,
        source_file=source_file,
        title=title,
        parent_count=len(parents),
        chunk_count=len(children),
        created=True,
    )


async def delete_document_data(session: AsyncSession, milvus, doc_id: str) -> None:
    """按 doc_id 删除子向量、父块和文档记录。"""
    # 先移除可检索子块，数据库操作失败时可安全重试删除。
    await run_in_threadpool(delete_vectors, milvus, doc_id)
    await session.execute(delete(ParentChunk).where(ParentChunk.doc_id == doc_id))
    await session.execute(delete(DocumentRecord).where(DocumentRecord.doc_id == doc_id))
    await session.commit()
