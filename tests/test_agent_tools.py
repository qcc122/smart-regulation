import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.modules.agent.tools import RetrievalContext, search_regulations


class RetrievalToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_tool_keeps_sources_and_parent_text_together(self):
        source = {
            "citation_id": "one", "title": "法规", "source_file": "法规.pdf",
            "chapter": "第一章", "article_no": "第一条", "page": None,
            "content": "父块原文",
        }

        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        writer = Mock()
        runtime = SimpleNamespace(
            state={"top_k": 2}, stream_writer=writer, tool_call_id="call-1",
            context=RetrievalContext(lambda: Session(), object()),
        )
        with patch("app.modules.agent.tools.retrieve_contexts", new=AsyncMock(return_value=[source])) as retrieve:
            command = await search_regulations.coroutine("查询", runtime)

        retrieve.assert_awaited_once()
        self.assertEqual(command.update["sources"], [source])
        self.assertIn("父块原文", command.update["messages"][0].content)
        self.assertIn("页码未知", command.update["messages"][0].content)
        self.assertEqual(command.update["messages"][0].tool_call_id, "call-1")
        writer.assert_called_once_with({"type": "sources", "sources": [source]})


if __name__ == "__main__":
    unittest.main()
