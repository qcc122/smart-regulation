"""文档上传、列表与删除路由。"""
import logging
import os
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.common.deps import get_milvus, get_session
from app.common.utils import ok
from app.core.config import MAX_UPLOAD_MB, UPLOAD_DIR
from app.modules.document.models import DocumentRecord
from app.modules.document.parser import DocumentParseError
from app.modules.document.service import delete_document_data, ingest_document

router = APIRouter()
logger = logging.getLogger("rag")
_DOC_ID_RE = re.compile(r"^[a-f0-9]{12}$")
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def _remove_file(path):
    try:
        os.remove(path)
    except OSError:
        pass

@router.get("/api/documents")
async def get_documents(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(DocumentRecord.doc_id, DocumentRecord.chunk_count)
        .where(DocumentRecord.status == "ready")
        .order_by(DocumentRecord.created_at.desc())
    )
    return ok([{"doc_id": row.doc_id, "chunk_count": row.chunk_count} for row in rows])


@router.delete("/api/documents/{doc_id}")
async def remove_document(
    doc_id: str,
    milvus=Depends(get_milvus),
    session: AsyncSession = Depends(get_session),
):
    if not _DOC_ID_RE.match(doc_id):
        raise HTTPException(404, "文档不存在")
    record = await session.get(DocumentRecord, doc_id)
    if record is None:
        raise HTTPException(404, "文档不存在")
    await delete_document_data(session, milvus, doc_id)
    # 只删除这条文档记录对应的上传副本，不使用前缀匹配清理其它文件。
    _remove_file(os.path.join(UPLOAD_DIR, f"{doc_id}_{record.source_file}"))
    logger.info("文档已删除 doc_id=%s", doc_id)
    return ok(message="删除成功")


@router.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    milvus=Depends(get_milvus),
    session: AsyncSession = Depends(get_session),
):
    """上传文档并调用本地初始化脚本共用的入库 pipeline。"""
    filename = os.path.basename(file.filename or "")
    if not filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(400, "仅支持 pdf/docx 文件")
    # 多读 1 字节即可判断超限，避免把超大文件完整读入内存。
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "文件超过大小限制（%dMB）" % MAX_UPLOAD_MB)

    doc_id = uuid.uuid4().hex[:12]
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, "%s_%s" % (doc_id, filename))
    try:
        # 上传副本使用独立文件名；后续解析和两侧存储由共享 pipeline 协调。
        await run_in_threadpool(_write_upload, file_path, data)
        result = await ingest_document(session, milvus, file_path, doc_id, filename)
        if not result.created:
            _remove_file(file_path)
            return ok({
                "doc_id": result.doc_id,
                "filename": result.source_file,
                "title": result.title,
                "chunk_count": result.chunk_count,
            }, "文档已存在")
    except DocumentParseError as exc:
        _remove_file(file_path)
        raise HTTPException(400, str(exc)) from None
    except HTTPException:
        _remove_file(file_path)
        raise
    except Exception:
        _remove_file(file_path)
        logger.exception("文档入库失败 doc_id=%s file=%s", doc_id, filename)
        raise HTTPException(500, "文档处理失败，请稍后重试")

    logger.info("文档上传成功 doc_id=%s file=%s chunks=%d", result.doc_id, filename, result.chunk_count)
    return ok({"doc_id": result.doc_id, "filename": filename, "title": result.title,
               "chunk_count": result.chunk_count}, "上传成功")


def _write_upload(path: str, data: bytes) -> None:
    """把已限长读取的上传内容写入受控目录。"""
    with open(path, "wb") as destination:
        destination.write(data)
