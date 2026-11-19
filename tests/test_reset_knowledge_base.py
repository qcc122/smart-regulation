import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from scripts.reset_knowledge_base import (
    clear_uploaded_copies,
    drop_milvus_collection,
    reset_application_data,
    reset_postgres_documents,
)


class FakeSession:
    def __init__(self):
        self.executed = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement):
        self.executed.append(statement)

    async def commit(self):
        self.committed = True


class FailingConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _statement):
        raise RuntimeError("postgres unavailable")


class ResetKnowledgeBaseTests(unittest.IsolatedAsyncioTestCase):
    def test_drops_only_configured_langchain_collection(self):
        store = SimpleNamespace(col=object(), drop=Mock())
        with patch("scripts.reset_knowledge_base.create_milvus_store", return_value=store) as create:
            dropped = drop_milvus_collection("http://milvus:19530", "default", "rag_collection", 8)

        self.assertTrue(dropped)
        create.assert_called_once_with("http://milvus:19530", "default", "rag_collection", 8)
        store.drop.assert_called_once_with()

    def test_missing_collection_is_left_untouched(self):
        store = SimpleNamespace(col=None, drop=Mock())
        with patch("scripts.reset_knowledge_base.create_milvus_store", return_value=store):
            dropped = drop_milvus_collection("http://milvus:19530", "default", "rag_collection", 8)

        self.assertFalse(dropped)
        store.drop.assert_not_called()

    async def test_clears_only_document_tables_and_disposes_engine(self):
        session = FakeSession()
        engine = SimpleNamespace(dispose=AsyncMock())
        database = SimpleNamespace(engine=engine, session_factory=Mock(return_value=session))
        settings = SimpleNamespace(db=object())
        with patch("scripts.reset_knowledge_base.create_database", return_value=database), patch(
            "scripts.reset_knowledge_base.initialize_schema", new=AsyncMock()
        ) as initialize:
            await reset_postgres_documents(settings)

        initialize.assert_awaited_once_with(engine)
        self.assertEqual(len(session.executed), 2)
        self.assertTrue(session.committed)
        engine.dispose.assert_awaited_once()

    async def test_postgres_preflight_failure_happens_before_collection_drop(self):
        engine = SimpleNamespace(connect=Mock(return_value=FailingConnection()), dispose=AsyncMock())
        database = SimpleNamespace(engine=engine)
        settings = SimpleNamespace(
            db=object(),
            milvus_uri="http://milvus:19530",
            milvus_db_name="rag_db",
            milvus_collection_name="rag_collection",
        )
        with patch("scripts.reset_knowledge_base.create_database", return_value=database), patch(
            "scripts.reset_knowledge_base.initialize_schema", new=AsyncMock()
        ), patch("scripts.reset_knowledge_base.drop_milvus_collection") as drop_collection:
            with self.assertRaisesRegex(RuntimeError, "postgres unavailable"):
                await reset_application_data(settings)

        drop_collection.assert_not_called()
        engine.dispose.assert_awaited_once()

    def test_uploaded_copy_cleanup_only_removes_generated_document_names(self):
        with tempfile.TemporaryDirectory() as folder:
            generated = Path(folder) / "abcdef123456_law.pdf"
            unrelated = Path(folder) / "notes.pdf"
            bad_prefix = Path(folder) / "abcdef12345_law.pdf"
            generated.write_bytes(b"uploaded")
            unrelated.write_bytes(b"keep")
            bad_prefix.write_bytes(b"keep")

            removed = clear_uploaded_copies(folder)

            self.assertEqual(removed, 1)
            self.assertFalse(generated.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(bad_prefix.exists())

    def test_reset_cli_requires_explicit_confirmation(self):
        settings = SimpleNamespace(
            postgres_db="insurance",
            milvus_db_name="rag_db",
            milvus_collection_name="rag_collection",
        )
        with patch.object(sys, "argv", ["reset_knowledge_base"]), patch(
            "scripts.reset_knowledge_base.get_settings", return_value=settings
        ), patch("scripts.reset_knowledge_base.reset_application_data", new=AsyncMock()) as reset:
            from scripts.reset_knowledge_base import main

            self.assertEqual(main(), 2)

        reset.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
