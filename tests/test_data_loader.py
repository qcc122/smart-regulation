import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.document.splitter import parse_file, split_markdown


class FakeSection:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


class FakeChild:
    def __init__(self, page_content):
        self.page_content = page_content


class DataLoaderTests(unittest.TestCase):
    def test_extract_markdown_is_split_by_headers_then_recursive_chunks(self):
        settings = {}

        class FakeMarkdownHeaderTextSplitter:
            def __init__(self, **kwargs):
                settings["headers"] = kwargs

            def split_text(self, markdown):
                settings["markdown"] = markdown
                return [FakeSection("第一条 建设单位应当保存资料。", {"h1": "第一章 总则", "h2": "第一条 建设单位"})]

        class FakeRecursiveCharacterTextSplitter:
            def __init__(self, **kwargs):
                settings["chunks"] = kwargs

            def split_documents(self, sections):
                return [FakeChild(sections[0].page_content)]

        fake_splitters = types.ModuleType("langchain_text_splitters")
        fake_splitters.MarkdownHeaderTextSplitter = FakeMarkdownHeaderTextSplitter
        fake_splitters.RecursiveCharacterTextSplitter = FakeRecursiveCharacterTextSplitter

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "建设规定.pdf"
            path.write_bytes(b"pdf")
            with (
                patch("app.modules.document.splitter.parse_document", return_value="# 第一章 总则\n第一条 建设单位应当保存资料。"),
                patch.dict(sys.modules, {"langchain_text_splitters": fake_splitters}),
            ):
                chunks = parse_file(str(path), doc_id="doc-123")

        self.assertEqual(settings["markdown"], "# 第一章 总则\n第一条 建设单位应当保存资料。")
        self.assertEqual(settings["headers"]["headers_to_split_on"], [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")])
        self.assertEqual(settings["chunks"]["chunk_size"], 500)
        self.assertEqual(settings["chunks"]["chunk_overlap"], 50)
        self.assertEqual(chunks[0]["content"], "第一章 总则\n第一条 建设单位\n第一条 建设单位应当保存资料。")
        self.assertEqual(chunks[0]["metadata"]["source_file"], "建设规定.pdf")
        self.assertEqual(chunks[0]["metadata"]["article_no"], "第一条 建设单位")
        self.assertEqual(chunks[0]["metadata"]["doc_id"], "doc-123")
        self.assertTrue(chunks[0]["metadata"]["parent_id"])

    def test_markdown_sections_are_parent_chunks_and_children_share_parent_id(self):
        class FakeMarkdownHeaderTextSplitter:
            def __init__(self, **kwargs):
                pass

            def split_text(self, markdown):
                return [FakeSection("完整章节正文", {"h1": "第一章 总则", "h2": "第一条 建设单位"})]

        class FakeRecursiveCharacterTextSplitter:
            def __init__(self, **kwargs):
                pass

            def split_documents(self, sections):
                return [FakeChild("章节片段")]

        fake_splitters = types.ModuleType("langchain_text_splitters")
        fake_splitters.MarkdownHeaderTextSplitter = FakeMarkdownHeaderTextSplitter
        fake_splitters.RecursiveCharacterTextSplitter = FakeRecursiveCharacterTextSplitter
        with patch.dict(sys.modules, {"langchain_text_splitters": fake_splitters}):
            parents, children = split_markdown(
                "# 第一章 总则\n## 第一条 建设单位\n完整章节正文",
                doc_id="doc-456",
                source_file="建设规定.pdf",
                title="建设规定",
            )

        self.assertEqual(parents[0]["content"], "完整章节正文")
        self.assertEqual(parents[0]["section_path"], ["第一章 总则", "第一条 建设单位"])
        self.assertEqual(children[0]["metadata"]["parent_id"], parents[0]["parent_id"])
        self.assertEqual(children[0]["content"], "第一章 总则\n第一条 建设单位\n章节片段")

    def test_headerless_markdown_falls_back_to_a_single_parent_section(self):
        class FakeMarkdownHeaderTextSplitter:
            def __init__(self, **kwargs):
                pass

            def split_text(self, markdown):
                self.markdown = markdown
                return []

        class FakeRecursiveCharacterTextSplitter:
            def __init__(self, **kwargs):
                pass

            def split_documents(self, sections):
                return [FakeChild(sections[0].page_content)]

        fake_splitters = types.ModuleType("langchain_text_splitters")
        fake_splitters.MarkdownHeaderTextSplitter = FakeMarkdownHeaderTextSplitter
        fake_splitters.RecursiveCharacterTextSplitter = FakeRecursiveCharacterTextSplitter
        fake_core = types.ModuleType("langchain_core")
        fake_core.__path__ = []
        fake_documents = types.ModuleType("langchain_core.documents")
        fake_documents.Document = FakeSection

        with patch.dict(sys.modules, {
            "langchain_text_splitters": fake_splitters,
            "langchain_core": fake_core,
            "langchain_core.documents": fake_documents,
        }):
            parents, children = split_markdown(
                "无标题的法规正文。",
                doc_id="doc-789",
                source_file="法规.pdf",
                title="法规",
            )

        self.assertEqual(parents[0]["content"], "无标题的法规正文。")
        self.assertEqual(parents[0]["section_path"], [])
        self.assertEqual(children[0]["content"], "无标题的法规正文。")


if __name__ == "__main__":
    unittest.main()
