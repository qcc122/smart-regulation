import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.modules.agent import repository as retriever


class FakeDocument:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


class RetrieverTests(unittest.TestCase):
    def setUp(self):
        fake_core = types.ModuleType("langchain_core")
        fake_core.__path__ = []
        fake_documents = types.ModuleType("langchain_core.documents")
        fake_documents.Document = FakeDocument
        self.document_patch = patch.dict(sys.modules, {
            "langchain_core": fake_core,
            "langchain_core.documents": fake_documents,
        })
        self.document_patch.start()
        self.addCleanup(self.document_patch.stop)

    def test_add_document_writes_langchain_documents_with_parent_metadata(self):
        store = Mock()
        store.collection_name = "rag_collection"
        chunks = [{
            "content": "第一条正文",
            "metadata": {
                "parent_id": "parent-uuid",
                "child_index": 1,
                "section_path": ["第一章 总则", "第一条"],
                "source_file": "法规.pdf",
            },
        }]

        retriever.add_document(store, "doc-123", chunks)

        store.add_documents.assert_called_once()
        documents = store.add_documents.call_args.kwargs["documents"]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].page_content, "第一条正文")
        self.assertEqual(documents[0].metadata["doc_id"], "doc-123")
        self.assertEqual(documents[0].metadata["parent_id"], "parent-uuid")
        self.assertEqual(documents[0].metadata["section_path"], ["第一章 总则", "第一条"])

    def test_delete_document_uses_langchain_filter_expression(self):
        store = Mock()
        store.collection_name = "rag_collection"
        store.col = object()

        retriever.delete_document(store, "abcdef123456")

        store.delete.assert_called_once_with(expr='doc_id == "abcdef123456"')

    def test_search_returns_langchain_documents_and_scores(self):
        fake_pymilvus = types.ModuleType("pymilvus")
        fake_pymilvus.FunctionType = SimpleNamespace(RERANK="rerank")
        fake_pymilvus.Function = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
        store = Mock()
        store.collection_name = "rag_collection"
        store.col = object()
        store.similarity_search_with_score.return_value = [(
            FakeDocument("检索正文", {
                "doc_id": "doc-123",
                "parent_id": "parent-uuid",
                "child_index": 2,
                "title": "法规标题",
                "section_path": ["第一章"],
                "source_file": "法规.pdf",
            }),
            0.87,
        )]

        with patch.dict(sys.modules, {"pymilvus": fake_pymilvus}):
            results = retriever.search(store, "查询", top_k=3)

        call = store.similarity_search_with_score.call_args
        self.assertEqual(call.args, ("查询",))
        self.assertEqual(call.kwargs["k"], 3)
        self.assertEqual(call.kwargs["fetch_k"], 10)
        self.assertEqual(call.kwargs["reranker"].input_field_names, ["text"])
        self.assertEqual(call.kwargs["reranker"].params, {
            "reranker": "model", "provider": "siliconflow",
            "model_name": "BAAI/bge-reranker-v2-m3", "queries": ["查询"],
        })
        self.assertEqual(results, [{
            "doc_id": "doc-123",
            "parent_id": "parent-uuid",
            "child_index": 2,
            "content": "检索正文",
            "score": 0.87,
            "title": "法规标题",
            "article_no": None,
            "chapter": None,
            "page": None,
            "source_file": "法规.pdf",
            "effective_date": None,
            "status": None,
            "part_no": None,
        }])

    def test_search_on_missing_collection_returns_no_results(self):
        store = Mock()
        store.collection_name = "rag_collection"
        store.col = None

        self.assertEqual(retriever.search(store, "查询"), [])
        store.similarity_search_with_score.assert_not_called()


if __name__ == "__main__":
    unittest.main()
