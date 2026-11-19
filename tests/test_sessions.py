import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
from langchain.messages import AIMessage, HumanMessage

from app.modules.conversation.models import ChatSession
from app.modules.conversation.router import get_session_history, remove_session
from app.modules.conversation.service import save_session


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_answer_creates_title_and_followup_preserves_it(self):
        class Session:
            row = None

            async def get(self, model, session_id):
                return self.row

            def add(self, row):
                self.row = row

            async def commit(self):
                pass

        session = Session()
        await save_session(session, "thread-1", "第一条法规是什么")
        self.assertEqual(session.row.title, "第一条法规是什么")
        await save_session(session, "thread-1", "另一个问题")
        self.assertEqual(session.row.title, "第一条法规是什么")
        self.assertIsNotNone(session.row.updated_at)

    async def test_history_reads_checkpoint_and_delete_clears_it(self):
        now = datetime.now(timezone.utc)
        row = ChatSession(id="thread-1", title="法规咨询", created_at=now, updated_at=now)
        session = SimpleNamespace(
            get=AsyncMock(return_value=row),
            delete=AsyncMock(),
            commit=AsyncMock(),
        )
        graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={
            "messages": [HumanMessage(content="问题"), AIMessage(
                content=[{"type": "text", "text": "回答", "index": 0}],
                additional_kwargs={"sources": [{"doc_id": "法规", "content": "父块原文"}]}
            )],
        })))
        history = await get_session_history("thread-1", session, graph)
        self.assertEqual([m["role"] for m in history["data"]["messages"]], ["user", "assistant"])
        self.assertEqual(history["data"]["title"], "法规咨询")
        self.assertEqual(history["data"]["messages"][1]["content"], "回答")
        self.assertEqual(history["data"]["messages"][1]["sources"][0]["content"], "父块原文")

        checkpointer = SimpleNamespace(adelete_thread=AsyncMock())
        await remove_session("thread-1", session, checkpointer)
        checkpointer.adelete_thread.assert_awaited_once_with("thread-1")
        session.delete.assert_awaited_once_with(row)

    async def test_missing_session_does_not_delete_checkpoint(self):
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        checkpointer = SimpleNamespace(adelete_thread=AsyncMock())
        with self.assertRaises(HTTPException) as raised:
            await remove_session("missing", session, checkpointer)
        self.assertEqual(raised.exception.status_code, 404)
        checkpointer.adelete_thread.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
