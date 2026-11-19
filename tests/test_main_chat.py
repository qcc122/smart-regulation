import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from langchain.messages import AIMessage, AIMessageChunk

from app.common.deps import get_conversation_graph, get_database
from app.main import app
from app.modules.chat.router import ChatRequest, chat
from app.modules.chat.service import stream_chat


class FakeRun:
    def __init__(self, events):
        self.events = events
        self.extensions = {"chat_events": self.convert()}
    async def __aenter__(self): return self
    async def __aexit__(self, *args): await self.events.aclose()
    def __aiter__(self): return self.convert()
    async def convert(self):
        async for part in self.events:
            yield {"method": part["type"], "params": {"data": part["data"], "namespace": part["ns"]}}


class FakeGraph:
    def __init__(self, events): self.events = events
    async def astream_events(self, *args, **kwargs):
        assert kwargs["version"] == "v3"
        return FakeRun(self.events())


class FakeSession:
    def __init__(self):
        self.rows = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, _model, session_id):
        return self.rows.get(session_id)

    def add(self, row):
        self.rows[row.id] = row

    async def commit(self):
        pass


class ChatGraphRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_uses_graph_result_and_thread_id(self):
        source = {"citation_id": "one", "content": "法规原文"}
        graph = SimpleNamespace(ainvoke=AsyncMock(return_value={
            "answer": "根据法规[1]", "sources": [source],
        }))
        session = FakeSession()
        db = SimpleNamespace(session_factory=lambda: session)
        result = await chat(ChatRequest(question="问题", session_id="thread-1", top_k=2), graph, db)

        self.assertEqual(result["data"], {
            "session_id": "thread-1", "answer": "根据法规[1]", "sources": [source],
        })
        graph.ainvoke.assert_awaited_once_with(
            {"messages": [{"role": "user", "content": "问题"}], "top_k": 2},
            {"configurable": {"thread_id": "thread-1"}},
        )
        self.assertEqual(session.rows["thread-1"].title, "问题")

    async def test_stream_emits_sources_before_final_answer(self):
        source = {"citation_id": "one", "content": "法规原文"}

        async def events(*args, **kwargs):
            yield {"type": "tasks", "ns": (), "data": {"id": "intent-1", "name": "intent", "input": {}}}
            yield {"type": "tasks", "ns": (), "data": {"id": "intent-1", "name": "intent", "result": {"intent": "rag"}, "error": None}}
            tool_call = AIMessage(content="", tool_calls=[
                {"name": "search_regulations", "args": {"query": "问题"}, "id": "call-1"},
            ])
            yield {"type": "tasks", "ns": ("rag",), "data": {
                "id": "tool-1", "name": "tools", "input": {"messages": [tool_call]},
            }}
            yield {"type": "custom", "ns": ("rag",), "data": {"type": "sources", "sources": [source]}}
            yield {"type": "messages", "ns": ("rag",), "data": (
                {"event": "content-block-delta", "index": 0,
                 "delta": {"type": "text-delta", "text": "根据法规"}}, {"langgraph_node": "model"},
            )}
            yield {"type": "tasks", "ns": ("rag",), "data": {
                "id": "tool-1", "name": "tools", "result": {}, "error": None,
            }}
            yield {"type": "values", "ns": (), "data": {
                "answer": "根据法规[1]", "sources": [source],
            }}

        graph = FakeGraph(events)
        session = FakeSession()
        db = SimpleNamespace(session_factory=lambda: session)
        response = stream_chat(ChatRequest(question="问题", session_id="thread-1"), graph, db)
        frames = [frame async for frame in response]
        payloads = frames

        self.assertEqual(payloads[:3], [
            {"type": "node", "id": "intent-1", "name": "intent", "status": "running"},
            {"type": "node", "id": "intent-1", "name": "intent", "status": "success"},
            {"type": "tool", "id": "tool-1", "name": "search_regulations", "status": "running"},
        ])
        self.assertIn({"type": "sources", "sources": [source]}, payloads)
        self.assertIn({"type": "tool", "id": "tool-1", "name": "search_regulations", "status": "success"}, payloads)
        self.assertEqual([item for item in payloads if item["type"] == "delta"], [
            {"type": "delta", "content": "根据法规"},
        ])
        self.assertEqual(payloads[-1], {
            "type": "done", "session_id": "thread-1",
            "answer": "根据法规[1]", "sources": [source],
        })
        self.assertEqual(session.rows["thread-1"].title, "问题")

    async def test_stream_error_has_one_terminal_event_without_internal_details(self):
        async def events(*args, **kwargs):
            yield {"type": "tasks", "ns": (), "data": {"id": "x", "name": "rag", "input": {}}}
            raise RuntimeError("secret=private")

        graph = FakeGraph(events)
        db = SimpleNamespace(session_factory=lambda: FakeSession())
        response = stream_chat(ChatRequest(question="问题", session_id="thread-1"), graph, db)
        payloads = [frame async for frame in response]

        self.assertEqual(payloads[-1], {"type": "error", "message": "问答失败，请稍后重试"})
        self.assertNotIn("private", str(payloads))
        self.assertNotIn("done", [item["type"] for item in payloads])

    async def test_stream_sends_draft_before_graph_finishes_then_done_corrects_it(self):
        async def events(*args, **kwargs):
            yield {"type": "messages", "ns": ("rag",), "data": (
                AIMessageChunk(content="错误草稿"), {"langgraph_node": "model"},
            )}
            self.assertTrue(received_delta)
            yield {"type": "values", "ns": (), "data": {"answer": "暂未找到法规依据", "sources": []}}

        graph = FakeGraph(events)
        db = SimpleNamespace(session_factory=lambda: FakeSession())
        response = stream_chat(ChatRequest(question="问题", session_id="thread-1"), graph, db)
        received_delta = False
        payloads = []
        async for frame in response:
            if frame["type"] == "delta": received_delta = True
            payloads.append(frame)

        self.assertEqual([item for item in payloads if item["type"] == "delta"], [
            {"type": "delta", "content": "错误草稿"},
        ])
        self.assertEqual(payloads[-1]["answer"], "暂未找到法规依据")

    async def test_closing_stream_closes_graph_iterator(self):
        closed = False

        async def events(*args, **kwargs):
            nonlocal closed
            try:
                yield {"type": "tasks", "ns": (), "data": {"id": "i", "name": "intent", "input": {}}}
                yield {"type": "values", "ns": (), "data": {"answer": "不会执行", "sources": []}}
            finally:
                closed = True

        graph = FakeGraph(events)
        db = SimpleNamespace(session_factory=lambda: FakeSession())
        response = stream_chat(ChatRequest(question="问题", session_id="thread-1"), graph, db)
        await anext(response)
        await response.aclose()

        self.assertTrue(closed)


class ChatStreamHttpTests(unittest.TestCase):
    def test_http_stream_uses_sse_content_type_and_terminal_done(self):
        async def events(*args, **kwargs):
            yield {"type": "values", "ns": (), "data": {"answer": "回答", "sources": []}}

        app.dependency_overrides[get_conversation_graph] = lambda: FakeGraph(events)
        app.dependency_overrides[get_database] = lambda: SimpleNamespace(session_factory=lambda: FakeSession())
        client = TestClient(app)
        try:
            response = client.post("/api/chat/stream", json={"question": "问题", "session_id": "thread-1"})
        finally:
            client.close()
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        payloads = [json.loads(frame.removeprefix("data: ").strip()) for frame in response.text.strip().split("\n\n")]
        self.assertEqual(payloads[-1]["type"], "done")


class RealV3StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_v3_model_sends_multiple_deltas_before_node_returns(self):
        from typing import TypedDict
        from langchain_core.language_models.fake_chat_models import FakeListChatModel
        from langgraph.graph import StateGraph, START

        class State(TypedDict):
            answer: str

        model = FakeListChatModel(responses=["你好"], sleep=0.02)
        node_finished = False

        async def reply(state):
            nonlocal node_finished
            message = await model.ainvoke("你好")
            node_finished = True
            return {"answer": message.text}

        builder = StateGraph(State)
        builder.add_node("reply", reply)
        builder.add_edge(START, "reply")
        chunks = []
        early_chunks = []
        async for event in stream_chat(ChatRequest(question="你好"), builder.compile(), SimpleNamespace(session_factory=FakeSession)):
            if event["type"] == "delta":
                chunks.append(event["content"])
                early_chunks.append(not node_finished)
        self.assertEqual("".join(chunks), "你好")
        self.assertGreater(len(chunks), 1)
        self.assertTrue(any(early_chunks))

    async def test_real_graph_v3_emits_tasks_custom_and_checked_answer(self):
        from typing import TypedDict
        from langgraph.graph import StateGraph, START
        from langgraph.config import get_stream_writer

        class State(TypedDict):
            answer: str
            sources: list

        async def answer(state):
            get_stream_writer()({"type": "sources", "sources": []})
            return {"answer": "已校验回答", "sources": []}

        builder = StateGraph(State)
        builder.add_node("answer", answer)
        builder.add_edge(START, "answer")
        db = SimpleNamespace(session_factory=FakeSession)
        events = [event async for event in stream_chat(ChatRequest(question="问题"), builder.compile(), db)]
        self.assertEqual([event["type"] for event in events], ["node", "sources", "node", "delta", "done"])
        self.assertEqual(events[0]["status"], "running")
        self.assertEqual(events[2]["status"], "success")


if __name__ == "__main__":
    unittest.main()
