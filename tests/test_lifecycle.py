import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pydantic import SecretStr

from app.core.config import DbSettings
from app.core.database import Database, database_lifespan
from app.common.deps import get_session


class FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.closed = True

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class DatabaseLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = DbSettings(
            host="postgres",
            port=5432,
            name="insurance",
            user="insurance",
            password=SecretStr("password"),
        )

    async def test_lifespan_stores_database_and_disposes_engine(self):
        engine = SimpleNamespace(dispose=AsyncMock())
        database = Database(engine=engine, session_factory=Mock())
        app = SimpleNamespace(state=SimpleNamespace())

        with patch("app.core.database.create_database", return_value=database), patch(
            "app.core.database.initialize_schema", new=AsyncMock()
        ) as initialize:
            async with database_lifespan(app, self.settings):
                self.assertIs(app.state.database, database)

        initialize.assert_awaited_once_with(engine)
        engine.dispose.assert_awaited_once()
        self.assertFalse(hasattr(app.state, "database"))

    async def test_request_session_commits_and_closes_after_success(self):
        session = FakeSession()
        factory = Mock(return_value=session)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            database=SimpleNamespace(session_factory=factory)
        )))

        dependency = get_session(request)
        self.assertIs(await anext(dependency), session)
        with self.assertRaises(StopAsyncIteration):
            await anext(dependency)

        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)
        self.assertTrue(session.closed)

    async def test_request_session_rolls_back_and_closes_after_exception(self):
        session = FakeSession()
        factory = Mock(return_value=session)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            database=SimpleNamespace(session_factory=factory)
        )))
        dependency = get_session(request)
        await anext(dependency)

        with self.assertRaisesRegex(RuntimeError, "request failed"):
            await dependency.athrow(RuntimeError("request failed"))

        self.assertFalse(session.committed)
        self.assertTrue(session.rolled_back)
        self.assertTrue(session.closed)

    async def test_main_lifespan_builds_graph_once_and_cleans_up(self):
        from app.main import lifespan

        app = SimpleNamespace(state=SimpleNamespace())
        settings = SimpleNamespace(
            db=object(), rag=SimpleNamespace(
                milvus_uri="test", milvus_db_name="test", milvus_collection_name="test", vector_dim=1
            ),
            zhipu_api_key=None, postgres_password=None,
            siliconflow_api_key=None, mineru_token=None,
            validate_required=Mock(),
        )
        saver = object()
        tools = [object()]

        @asynccontextmanager
        async def database_lifecycle(app, _settings):
            app.state.database = SimpleNamespace(session_factory=object())
            yield

        @asynccontextmanager
        async def milvus_lifecycle(app, *_args):
            app.state.milvus = object()
            yield

        @asynccontextmanager
        async def conversation_lifecycle(app, *_args):
            app.state.conversation_checkpointer = saver
            yield tools
            del app.state.conversation_checkpointer

        with patch("app.main.get_settings", return_value=settings), patch(
            "app.main.configure_logging"
        ), patch("app.main.database_lifespan", database_lifecycle), patch(
            "app.main.milvus_lifespan", milvus_lifecycle
        ), patch("app.main.conversation_lifespan", conversation_lifecycle), patch(
            "app.main.build_graph", return_value=object(), create=True
        ) as build:
            async with lifespan(app):
                self.assertIs(app.state.conversation_graph, build.return_value)
                build.assert_called_once_with(
                    saver, app.state.database.session_factory, app.state.milvus, settings.rag, tools
                )

        self.assertFalse(hasattr(app.state, "conversation_graph"))


if __name__ == "__main__":
    unittest.main()
