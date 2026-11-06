"""RAG API 入口，启动: uvicorn app.main:app --reload"""
import json as json_lib
import logging
import os
import re
import time
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from zai import ZhipuAiClient

from app.config import GLM_MODEL, MAX_UPLOAD_MB, SESSION_TTL, UPLOAD_DIR, ZHIPU_API_KEY
from app.data_loader import parse_file
from app.retriever import add_document, delete_document, ensure_collection, list_documents, search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("rag")

app = FastAPI(title="住建法规RAG问答系统", version="1.0.0")
# 会话历史（内存存储，带过期时间，重启即清空）
_sessions = {}
MAX_SESSIONS = 500
_DOC_ID_RE = re.compile(r"^[a-f0-9]{12}$")
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}


@app.exception_handler(HTTPException)
async def http_exc_handler(request, exc):
    return JSONResponse(status_code=exc.status_code,
                        content={"code": exc.status_code, "message": exc.detail, "data": None})


@app.exception_handler(Exception)
async def generic_exc_handler(request, exc):
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content={"code": 500, "message": "服务器内部错误", "data": None})


@app.on_event("startup")
def startup():
    ensure_collection()
    logger.info("服务启动完成，Milvus 集合已就绪")


def _get_history(session_id):
    """取会话历史，顺带清理过期会话"""
    now = time.time()
    for k in [k for k, v in _sessions.items() if now - v["ts"] > SESSION_TTL]:
        _sessions.pop(k, None)
    item = _sessions.get(session_id)
    if item is None:
        return []
    item["ts"] = now
    return item["messages"]


def _save_history(session_id, messages):
    """保存会话历史，超过上限时淘汰最久未活跃的会话"""
    if len(_sessions) >= MAX_SESSIONS:
        oldest = min(_sessions, key=lambda k: _sessions[k]["ts"])
        _sessions.pop(oldest, None)
    _sessions[session_id] = {"messages": messages[-20:], "ts": time.time()}


def _remove_file(path):
    try:
        os.remove(path)
    except OSError:
        pass


@app.get("/api/health")
def health():
    return ok({"status": "up"})


@app.get("/api/documents")
def get_documents():
    return ok(list_documents())


@app.delete("/api/documents/{doc_id}")
def remove_document(doc_id: str):
    if not _DOC_ID_RE.match(doc_id):
        raise HTTPException(404, "文档不存在")
    delete_document(doc_id)
    logger.info("文档已删除 doc_id=%s", doc_id)
    return ok(message="删除成功")


@app.post("/api/documents/upload")
def upload_document(file: UploadFile = File(...)):
    """上传文档：保存 -> 解析切分 -> 向量化入库（失败自动清理）"""
    filename = os.path.basename(file.filename or "")
    if not filename.endswith((".pdf", ".docx")):
        raise HTTPException(400, "仅支持 pdf/docx 文件")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "文件超过大小限制（%dMB）" % MAX_UPLOAD_MB)

    doc_id = uuid.uuid4().hex[:12]
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, "%s_%s" % (doc_id, filename))
    try:
        with open(file_path, "wb") as f:
            f.write(data)
        chunks = parse_file(file_path)
        if not chunks:
            raise HTTPException(400, "文档解析结果为空")
        add_document(doc_id, chunks)
    except HTTPException:
        _remove_file(file_path)
        raise
    except Exception:
        _remove_file(file_path)
        logger.exception("文档入库失败 doc_id=%s file=%s", doc_id, filename)
        raise HTTPException(500, "文档处理失败，请稍后重试")

    logger.info("文档上传成功 doc_id=%s file=%s chunks=%d", doc_id, filename, len(chunks))
    return ok({"doc_id": doc_id, "filename": filename, "chunk_count": len(chunks)}, "上传成功")


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None
    top_k: int | None = None


@app.post("/api/chat")
def chat(req: ChatRequest):
    """问答：向量检索 -> 拼接 Prompt -> 大模型生成"""
    history = _get_history(req.session_id) if req.session_id else []
    contexts = search(req.question, req.top_k or 5)
    context = "\n\n".join("[%d] %s" % (i + 1, c["content"]) for i, c in enumerate(contexts))
    prompt = ("请根据以下参考资料回答问题，资料中没有的信息要如实说明，不要编造。\n\n"
              "参考资料：\n%s\n\n问题：%s" % (context, req.question))
    client = ZhipuAiClient(api_key=ZHIPU_API_KEY)
    response = client.chat.completions.create(
        model=GLM_MODEL,
        messages=history + [{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    answer = response.choices[0].message.content
    if req.session_id:
        history.append({"role": "user", "content": req.question})
        history.append({"role": "assistant", "content": answer})
        _save_history(req.session_id, history)
    return ok({"session_id": req.session_id or uuid.uuid4().hex[:12],
               "answer": answer,
               "sources": [{"doc_id": c["doc_id"], "content": c["content"]} for c in contexts]})


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE 流式问答：先推送引用来源，再逐块推送生成内容，最后给出完整答案终帧"""
    def frame(payload):
        return "data: " + json_lib.dumps(payload, ensure_ascii=False) + "\n\n"

    def generate():
        try:
            history = _get_history(req.session_id) if req.session_id else []
            contexts = search(req.question, req.top_k or 5)
            sources = [{"doc_id": c["doc_id"], "content": c["content"]} for c in contexts]
            yield frame({"type": "sources", "sources": sources})

            context = "\n\n".join("[%d] %s" % (i + 1, c["content"]) for i, c in enumerate(contexts))
            prompt = ("请根据以下参考资料回答问题，资料中没有的信息要如实说明，不要编造。\n\n"
                      "参考资料：\n%s\n\n问题：%s" % (context, req.question))
            client = ZhipuAiClient(api_key=ZHIPU_API_KEY)
            stream = client.chat.completions.create(
                model=GLM_MODEL,
                messages=history + [{"role": "user", "content": prompt}],
                temperature=0.1,
                stream=True,
            )

            parts = []
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                if not piece and isinstance(delta, dict):
                    piece = delta.get("content")
                if piece:
                    parts.append(piece)
                    yield frame({"type": "delta", "content": piece})

            answer = "".join(parts)
            if req.session_id:
                history.append({"role": "user", "content": req.question})
                history.append({"role": "assistant", "content": answer})
                _save_history(req.session_id, history)
            yield frame({
                "type": "done",
                "session_id": req.session_id or uuid.uuid4().hex[:12],
                "answer": answer,
                "sources": sources,
            })
        except Exception:
            logger.exception("流式问答生成失败")
            yield frame({"type": "error", "message": "生成失败，请稍后重试"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
