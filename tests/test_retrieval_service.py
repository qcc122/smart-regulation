import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.modules.document.models import DocumentRecord, ParentChunk
from app.modules.agent.tools import retrieve_contexts


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.rows)


class RetrievalServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_expands_and_deduplicates_parents_in_reranked_child_order(self):
        parent_one_id = UUID("00000000-0000-0000-0000-000000000001")
        parent_two_id = UUID("00000000-0000-0000-0000-000000000002")
        parent_one = ParentChunk(
            id=parent_one_id, doc_id="doc-one", parent_index=1,
            content="法规父块一全文", title="法规一",
            section_path=["第一章 总则", "第一条"], source_file="法规一.pdf",
        )
        parent_two = ParentChunk(
            id=parent_two_id, doc_id="doc-two", parent_index=1,
            content="法规父块二全文", title="法规二",
            section_path=["第二章 管理", "第五条"], source_file="法规二.pdf",
        )
        doc_one = DocumentRecord(
            doc_id="doc-one", content_sha256="1" * 64, source_file="法规一.pdf",
            source_type="pdf", title="法规一", status="ready", parent_count=1, chunk_count=2,
        )
        doc_two = DocumentRecord(
            doc_id="doc-two", content_sha256="2" * 64, source_file="法规二.pdf",
            source_type="pdf", title="法规二", status="ready", parent_count=1, chunk_count=1,
        )
        session = FakeSession([(parent_two, doc_two), (parent_one, doc_one)])
        child_hits = [
            {"parent_id": str(parent_one_id), "doc_id": "doc-one", "score": 0.9,
             "chapter": "第一章 总则", "article_no": "第一条"},
            {"parent_id": str(parent_one_id), "doc_id": "doc-one", "score": 0.8,
             "chapter": "第一章 总则", "article_no": "第一条"},
            {"parent_id": str(parent_two_id), "doc_id": "doc-two", "score": 0.7,
             "chapter": "第二章 管理", "article_no": "第五条"},
        ]
        with (
            patch("app.modules.agent.tools.search", return_value=child_hits) as search,
            patch(
                "app.modules.agent.tools.run_in_threadpool",
                new=AsyncMock(side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)),
            ),
        ):
            sources = await retrieve_contexts(
                session, object(), "查询问题", top_k=2,
            )

        search.assert_called_once_with(
            unittest.mock.ANY, "查询问题", 10
        )
        self.assertEqual([source["parent_id"] for source in sources], [str(parent_one_id), str(parent_two_id)])
        self.assertEqual(sources[0]["citation_id"], str(parent_one_id))
        self.assertEqual(sources[0]["content"], "法规父块一全文")
        self.assertEqual(sources[0]["source_file"], "法规一.pdf")
        self.assertIsNone(sources[0]["page"])
        self.assertEqual(sources[0]["section_path"], ["第一章 总则", "第一条"])
        self.assertEqual(sources[0]["retrieval_score"], 0.9)

    async def test_missing_parent_is_ignored(self):
        session = FakeSession([])
        with (
            patch("app.modules.agent.tools.search", return_value=[{
                "parent_id": "00000000-0000-0000-0000-000000000099", "doc_id": "doc", "score": 1,
            }]),
            patch(
                "app.modules.agent.tools.run_in_threadpool",
                new=AsyncMock(side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)),
            ),
        ):
            sources = await retrieve_contexts(
                session, object(), "查询", top_k=3
            )

        self.assertEqual(sources, [])


if __name__ == "__main__":
    unittest.main()
