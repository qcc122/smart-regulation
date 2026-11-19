import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx2
from pydantic import SecretStr

from app.core.config import DbSettings
from app.modules.conversation.service import create_mcp_http_client, conversation_lifespan


class McpTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_sse_has_no_read_deadline_but_connect_remains_bounded(self):
        async with create_mcp_http_client(timeout=httpx2.Timeout(5, read=300)) as client:
            self.assertIsNone(client.timeout.read)
            self.assertEqual(client.timeout.connect, 5)

    async def test_lifespan_does_not_hold_idle_mcp_connection(self):
        class Adapter:
            depth = 0

            async def __aenter__(self):
                self.depth += 1
                return self

            async def __aexit__(self, *args):
                self.depth -= 1

            async def list_tools(self):
                async with self:
                    return ["web-search"]

        adapter = Adapter()
        saver = SimpleNamespace(setup=AsyncMock())

        @asynccontextmanager
        async def saver_context(*args):
            yield saver

        settings = DbSettings(host="postgres", port=5432, name="smart_regulation",
                              user="regulation_app", password=SecretStr("test"))
        app = SimpleNamespace(state=SimpleNamespace())
        with (
            patch("langchain.mcp.MCPAdapter", return_value=adapter),
            patch("fastmcp.client.Client"),
            patch("app.modules.conversation.service.AsyncPostgresSaver.from_conn_string", saver_context),
        ):
            async with conversation_lifespan(app, settings, SimpleNamespace(zhipu_api_key=SecretStr("test"))) as tools:
                self.assertEqual(tools, ["web-search"])
                self.assertEqual(adapter.depth, 0)
                self.assertIs(app.state.conversation_checkpointer, saver)
