"""文档记录和 Markdown 章节父块的 PostgreSQL 模型。"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """项目 ORM 元数据基类。"""


class DocumentRecord(Base):
    """记录每份已入库文档的来源、去重摘要和处理结果。"""

    __tablename__ = "rag_documents"

    doc_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_file: Mapped[str] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16))
    parent_count: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParentChunk(Base):
    """完整 Markdown 章节；Milvus 子块通过 parent_id 回到这里。"""

    __tablename__ = "rag_parent_chunks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("rag_documents.doc_id", ondelete="CASCADE"),
        index=True,
    )
    parent_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(512))
    section_path: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    source_file: Mapped[str] = mapped_column(String(512))
