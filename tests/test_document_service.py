import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.document.service import delete_document_data, ingest_document
from app.modules.document.models import DocumentRecord, ParentChunk


class FakeSession:
    def __init__(self, existing=None, commit_error=None):
        self.existing = existing
        self.commit_error = commit_error
        self.rows = []
        self.commits = 0
        self.rollbacks = 0
        self.executed = []

    async def scalar(self, _query):
        return self.existing

    def add(self, row):
        self.rows.append(row)

    def add_all(self, rows):
        self.rows.extend(rows)

    async def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    async def rollback(self):
        self.rollbacks += 1

    async def execute(self, query):
        self.executed.append(query)


class DocumentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingests_markdown_sections_and_vectors_once(self):
        session = FakeSession()
        parent_id = "00000000-0000-0000-0000-000000000001"
        parents = [{
            "parent_id": parent_id,
            "doc_id": "doc-123",
            "parent_index": 1,
            "content": "完整章节",
            "title": "建设规定",
            "section_path": ["第一章 总则"],
            "source_file": "建设规定.pdf",
        }]
        children = [{"content": "第一章 总则\n片段", "metadata": {"parent_id": parent_id}}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "建设规定.pdf"
            path.write_bytes(b"pdf bytes")
            with (
                patch("app.modules.document.service.parse_document", return_value="# 第一章 总则\n完整章节"),
                patch("app.modules.document.service.split_markdown", return_value=(parents, children)),
                patch("app.modules.document.service.add_document") as add_vectors,
            ):
                result = await ingest_document(session, object(), path, "doc-123", "建设规定.pdf")

        add_vectors.assert_called_once_with(unittest.mock.ANY, "doc-123", children)
        self.assertTrue(result.created)
        self.assertEqual((result.parent_count, result.chunk_count), (1, 1))
        self.assertTrue(any(isinstance(row, DocumentRecord) for row in session.rows))
        self.assertTrue(any(isinstance(row, ParentChunk) for row in session.rows))
        self.assertEqual(session.commits, 1)

    async def test_same_file_returns_existing_ready_document_without_reparsing(self):
        existing = DocumentRecord(
            doc_id="doc-123",
            content_sha256="unused",
            source_file="建设规定.pdf",
            source_type="pdf",
            title="建设规定",
            status="ready",
            parent_count=2,
            chunk_count=5,
        )
        session = FakeSession(existing=existing)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "建设规定.pdf"
            path.write_bytes(b"same bytes")
            with patch("app.modules.document.service.parse_document") as parse:
                result = await ingest_document(session, object(), path, "new-id-12345", "other-name.pdf")

        parse.assert_not_called()
        self.assertFalse(result.created)
        self.assertEqual(result.doc_id, "doc-123")
        self.assertEqual(result.chunk_count, 5)

    async def test_database_failure_rolls_back_and_removes_inserted_vectors(self):
        session = FakeSession(commit_error=RuntimeError("database down"))
        parent_id = "00000000-0000-0000-0000-000000000002"
        parents = [{
            "parent_id": parent_id, "doc_id": "doc-123", "parent_index": 1,
            "content": "正文", "title": "建设规定", "section_path": [], "source_file": "建设规定.pdf",
        }]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "建设规定.pdf"
            path.write_bytes(b"pdf bytes")
            with (
                patch("app.modules.document.service.parse_document", return_value="正文"),
                patch("app.modules.document.service.split_markdown", return_value=(parents, [{"content": "正文", "metadata": {}}])),
                patch("app.modules.document.service.add_document"),
                patch("app.modules.document.service.delete_vectors") as delete_vectors,
            ):
                with self.assertRaisesRegex(RuntimeError, "database down"):
                    await ingest_document(session, object(), path, "doc-123", "建设规定.pdf")

        self.assertEqual(session.rollbacks, 1)
        delete_vectors.assert_called_once()

    async def test_delete_removes_vectors_and_database_rows(self):
        session = FakeSession()
        with patch("app.modules.document.service.delete_vectors") as delete_vectors:
            await delete_document_data(session, object(), "doc-123")

        delete_vectors.assert_called_once()
        self.assertEqual(len(session.executed), 2)
        self.assertEqual(session.commits, 1)


if __name__ == "__main__":
    unittest.main()
