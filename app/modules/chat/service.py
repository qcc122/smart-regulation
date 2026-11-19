"""聊天流式服务：消费 LangGraph v3 事件并输出 SSE 数据对象。"""
import logging
import uuid

from langgraph.stream import StreamChannel, StreamTransformer
from langchain.messages import AIMessageChunk

from app.modules.chat.schemas import ChatRequest
from app.modules.conversation.service import save_session

logger = logging.getLogger("rag")
NODE_NAMES = {"intent", "rag", "chat", "validate", "answer", "reply"}


class ChatEvents(StreamTransformer):
    """在内置转换器消费任务事件前，按原顺序收集父图及子图的聊天事件。"""

    before_builtins = True
    required_stream_modes = ("tasks", "custom", "values", "messages")

    def init(self):
        self.events = StreamChannel()
        return {"chat_events": self.events}

    def process(self, event):
        if event["method"] in self.required_stream_modes:
            self.events.push(event)
        return True


def _input(req: ChatRequest) -> dict:
    return {"messages": [{"role": "user", "content": req.question}], "top_k": req.top_k or 5}


def _config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


async def stream_chat(req: ChatRequest, graph, db):
    """实时发送模型正文增量，done 返回校验后的完整答案；退出时关闭 v3 运行。"""
    session_id = req.session_id or uuid.uuid4().hex[:12]
    sources_sent = False
    result = None
    tool_names = {}
    text_sent = False
    try:
        async with await graph.astream_events(
            _input(req), _config(session_id), version="v3",
            transformers=[ChatEvents],
        ) as stream:
            async for event in stream.extensions["chat_events"]:
                part = {"type": event["method"], "data": event["params"]["data"],
                        "ns": event["params"]["namespace"]}
                if part["type"] == "tasks":
                    task = part["data"]
                    name = task["name"]
                    if name == "tools":
                        if "input" in task:
                            messages = task["input"].get("messages", []) if isinstance(task["input"], dict) else []
                            calls = getattr(messages[-1], "tool_calls", []) if messages else []
                            tool_names[task["id"]] = calls[0]["name"] if len(calls) == 1 else name
                        name = tool_names.get(task["id"], name)
                    if task["name"] in NODE_NAMES or task["name"] in {"tools", "search_regulations"}:
                        yield ({
                            "type": "node" if task["name"] in NODE_NAMES else "tool",
                            "id": task["id"],
                            "name": name,
                            "status": "running" if "input" in task else "error" if task.get("error") else "success",
                        })
                elif (
                    part["type"] == "custom"
                    and isinstance(part["data"], dict)
                    and part["data"].get("type") == "sources"
                ):
                    sources_sent = True
                    yield (part["data"])
                elif part["type"] == "messages":
                    payload, metadata = part["data"]
                    if metadata.get("langgraph_node") not in {"model", "reply"}:
                        continue
                    text = ""
                    if isinstance(payload, dict):
                        if payload.get("event") == "content-block-delta":
                            delta = payload.get("delta", {})
                            if delta.get("type") == "text-delta":
                                text = delta.get("text", "")
                        elif payload.get("event") == "content-block-start":
                            block = payload.get("content", {})
                            if block.get("type") == "text":
                                text = block.get("text", "")
                    elif isinstance(payload, AIMessageChunk) and not payload.tool_call_chunks:
                        text = payload.text
                    if text:
                        if not sources_sent:
                            sources_sent = True
                            yield {"type": "sources", "sources": []}
                        text_sent = True
                        yield {"type": "delta", "content": text}
                elif part["type"] == "values" and not part["ns"]:
                    result = part["data"]
        if result is None:
            raise RuntimeError("图未返回最终状态")
        async with db.session_factory() as session:
            await save_session(session, session_id, req.question)
        sources = result.get("sources") or []
        if not sources_sent:
            yield ({"type": "sources", "sources": sources})
        answer = result["answer"]
        if answer and not text_sent:
            yield {"type": "delta", "content": answer}
        yield ({
            "type": "done", "session_id": session_id,
            "answer": answer, "sources": sources,
        })
    except Exception:
        logger.exception("流式问答失败")
        yield ({"type": "error", "message": "问答失败，请稍后重试"})
