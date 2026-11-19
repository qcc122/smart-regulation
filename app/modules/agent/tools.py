"""Agent 可调用的法规检索工具：子块重排后读取 PostgreSQL 父块。"""
import logging
from dataclasses import dataclass
from uuid import UUID

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.modules.agent.repository import search
from app.modules.document.models import DocumentRecord, ParentChunk

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalContext:
    """一次图运行所需资源，不写入会话 checkpoint。"""

    session_factory: object
    store: object


async def retrieve_contexts(session, store, query: str, top_k: int) -> list[dict]:
    """按 Milvus 重排的子块顺序去重，并取回可引用的父块。"""
    top_k = max(top_k, 1)
    child_hits = await run_in_threadpool(
        search, store, query, max(top_k, 10)
    )
    ordered_hits = {}
    parent_ids = []
    for hit in child_hits:
        try:
            parent_id = UUID(str(hit.get("parent_id")))
        except (ValueError, TypeError, AttributeError):
            logger.warning("Milvus 命中缺少有效 parent_id")
            continue
        key = str(parent_id)
        if key not in ordered_hits:
            ordered_hits[key] = hit
            parent_ids.append(parent_id)

    if not parent_ids:
        return []
    rows = await session.execute(
        select(ParentChunk, DocumentRecord)
        .join(DocumentRecord, DocumentRecord.doc_id == ParentChunk.doc_id)
        .where(ParentChunk.id.in_(parent_ids), DocumentRecord.status == "ready")
    )
    parents = {str(parent.id): (parent, record) for parent, record in rows.all()}
    contexts = []
    for parent_id, hit in ordered_hits.items():
        if parent_id not in parents:
            logger.warning("Milvus 命中的父块在 PostgreSQL 中不存在")
            continue
        parent, record = parents[parent_id]
        contexts.append({
            "citation_id": parent_id,
            "parent_id": parent_id,
            "doc_id": record.doc_id,
            "title": parent.title,
            "source_file": parent.source_file,
            "page": None,
            "section_path": parent.section_path or [],
            "chapter": hit.get("chapter"),
            "article_no": hit.get("article_no"),
            "content": parent.content,
            "retrieval_score": hit.get("score"),
        })
    return contexts[:top_k]


def format_context(contexts: list[dict]) -> str:
    """给模型的来源编号与前端引用列表保持同一顺序。"""
    return "\n\n".join(
        "[%d] %s | %s %s | %s\n%s" % (
            index + 1,
            context.get("title") or context.get("source_file") or "未知法规",
            context.get("chapter") or "",
            context.get("article_no") or "",
            "第%s页" % context["page"] if context.get("page") is not None else "页码未知",
            context["content"],
        )
        for index, context in enumerate(contexts)
    )


@tool
async def search_regulations(query: str, runtime: ToolRuntime[RetrievalContext]) -> Command:
    """检索法规原文并返回带编号的依据；回答法规问题时必须先调用。"""
    context = runtime.context
    async with context.session_factory() as session:
        contexts = await retrieve_contexts(
            session, context.store, query, runtime.state.get("top_k", 5),
        )
    runtime.stream_writer({"type": "sources", "sources": contexts})
    return Command(update={
        "sources": contexts,
        "messages": [ToolMessage(
            content=format_context(contexts) if contexts else "未检索到可用法规依据。",
            tool_call_id=runtime.tool_call_id,
        )],
    })
