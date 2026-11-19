import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from scripts.init_documents import find_documents, ingest_directory


class FakeSession:
    def __init__(self):
        self.closed = False
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.closed = True

    async def rollback(self):
        self.rollbacks += 1


class InitDocumentsTests(unittest.IsolatedAsyncioTestCase):
    def test_finds_supported_documents_recursively_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a.PDF").write_bytes(b"pdf")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "b.docx").write_bytes(b"docx")

            found = find_documents(root)

        self.assertEqual([path.name for path in found], ["a.PDF", "b.docx"])

    async def test_ingests_each_file_and_continues_after_one_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("added.pdf", "duplicate.docx", "broken.pdf"):
                (root / name).write_bytes(b"source")

            sessions = []

            def session_factory():
                session = FakeSession()
                sessions.append(session)
                return session

            async def fake_ingest(_session, _milvus, path, doc_id, source_file):
                self.assertEqual(Path(path).name, source_file)
                self.assertEqual(len(doc_id), 12)
                if source_file == "broken.pdf":
                    raise RuntimeError("MinerU unavailable")
                return SimpleNamespace(created=source_file == "added.pdf", doc_id=doc_id)

            with patch("scripts.init_documents.ingest_document", new=AsyncMock(side_effect=fake_ingest)) as ingest:
                summary = await ingest_directory(root, session_factory, object())

        self.assertEqual(summary, {"added": 1, "skipped": 1, "failed": 1})
        self.assertEqual(ingest.await_count, 3)
        self.assertEqual(len(sessions), 3)
        self.assertTrue(all(session.closed for session in sessions))
        self.assertEqual(sum(session.rollbacks for session in sessions), 1)

    def test_missing_directory_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(NotADirectoryError, "资料夹不存在"):
                find_documents(Path(folder) / "missing")


if __name__ == "__main__":
    unittest.main()
