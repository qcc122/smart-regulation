import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.modules.agent import repository as retriever


class MilvusLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_exposes_langchain_store_and_removes_state(self):
        store = object()
        app = SimpleNamespace(state=SimpleNamespace())

        with patch("app.modules.agent.repository.create_milvus_store", return_value=store) as create_store:
            async with retriever.milvus_lifespan(app, "http://milvus:19530", "rag_db", "rag_collection", 8):
                self.assertIs(app.state.milvus, store)

        create_store.assert_called_once_with("http://milvus:19530", "rag_db", "rag_collection", 8)
        self.assertFalse(hasattr(app.state, "milvus"))

    async def test_lifespan_removes_state_after_context_error(self):
        store = object()
        app = SimpleNamespace(state=SimpleNamespace())

        with patch("app.modules.agent.repository.create_milvus_store", return_value=store):
            with self.assertRaisesRegex(RuntimeError, "server failure"):
                async with retriever.milvus_lifespan(app, "http://milvus:19530", "rag_db", "rag_collection", 8):
                    raise RuntimeError("server failure")

        self.assertFalse(hasattr(app.state, "milvus"))

    def test_store_uses_langchain_dynamic_metadata_without_admin_client(self):
        captured = {}

        class FakeStore:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        fake_langchain_milvus = types.ModuleType("langchain_milvus")
        fake_langchain_milvus.Milvus = FakeStore
        fake_langchain_milvus.BM25BuiltInFunction = Mock(return_value="bm25-function")

        with patch.dict("sys.modules", {
            "langchain_milvus": fake_langchain_milvus,
        }):
            retriever.create_milvus_store("http://milvus:19530", "default", "rag_collection", 8)

        self.assertEqual(captured["collection_name"], "rag_collection")
        self.assertEqual(captured["connection_args"], {"uri": "http://milvus:19530", "db_name": "default"})
        self.assertTrue(captured["enable_dynamic_field"])
        self.assertFalse(captured["drop_old"])
        self.assertEqual(captured["vector_field"], ["dense", "sparse"])
        self.assertEqual(captured["builtin_function"], "bm25-function")
        self.assertNotIn("primary_field", captured)
        self.assertNotIn("text_field", captured)
        self.assertNotIn("index_params", captured)
        fake_langchain_milvus.BM25BuiltInFunction.assert_called_once_with(
            analyzer_params={"type": "chinese"}
        )

if __name__ == "__main__":
    unittest.main()
