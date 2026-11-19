"""MinerU Markdown 的章节切分与向量化。"""
import os
from uuid import uuid4

from app.core.config import EMBED_MODEL, ZHIPU_API_KEY
from app.modules.document.parser import parse_document


def split_markdown(
    markdown: str,
    *,
    doc_id: str,
    source_file: str,
    title: str,
) -> tuple[list[dict], list[dict]]:
    """将 Markdown 标题章节作为父块，并递归生成带 parent_id 的子块。"""
    from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "h1"),
            ("##", "h2"),
            ("###", "h3"),
            ("####", "h4"),
        ],
        strip_headers=True,
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "；", ";", "，", ",", ""],
        keep_separator="end",
    )

    sections = header_splitter.split_text(markdown)
    if not sections and markdown.strip():
        from langchain_core.documents import Document

        sections = [Document(page_content=markdown, metadata={})]

    parents = []
    children = []
    for section in sections:
        section_path = [str(value) for value in section.metadata.values() if value]
        parent_id = str(uuid4())
        parents.append({
            "parent_id": parent_id,
            "doc_id": doc_id,
            "parent_index": len(parents) + 1,
            "content": section.page_content,
            "title": title,
            "section_path": section_path,
            "source_file": source_file,
        })

        # 标题不保留在切分正文中时，将完整标题路径加回子块，避免失去章节上下文。
        section_header = "\n".join(section_path)
        for part_no, child in enumerate(child_splitter.split_documents([section]), 1):
            content = f"{section_header}\n{child.page_content}" if section_header else child.page_content
            article_no = next(
                (heading for heading in reversed(section_path) if heading.startswith("第") and "条" in heading),
                "",
            )
            chapter_path = section_path[:-1] if article_no else section_path
            children.append({
                "content": content,
                "metadata": {
                    "doc_id": doc_id,
                    "parent_id": parent_id,
                    "child_index": part_no,
                    "title": title,
                    "source_file": source_file,
                    "section_path": section_path,
                    "chapter": " / ".join(chapter_path),
                    "article_no": article_no,
                    # Markdown 提取不保证页码；引用定位使用标题路径。
                    "page": None,
                    "effective_date": "",
                    "status": "unknown",
                    "part_no": part_no,
                },
            })
    return parents, children


def parse_file(file_path: str, filename: str | None = None, doc_id: str | None = None) -> list[dict]:
    """调用 MinerU 提取 Markdown，返回供向量库使用的子块。"""
    source_name = str(filename or os.path.basename(file_path)).replace("\\", "/").rsplit("/", 1)[-1]
    markdown = parse_document(file_path, source_name)
    title = os.path.splitext(source_name)[0]
    _, chunks = split_markdown(
        markdown,
        doc_id=doc_id or uuid4().hex[:12],
        source_file=source_name,
        title=title,
    )
    return chunks


def embed_texts(texts: list[str], dim: int = 1024) -> list[list[float]]:
    """批量向量化（embedding 接口单次最多 64 条）。"""
    from zai import ZhipuAiClient

    client = ZhipuAiClient(api_key=ZHIPU_API_KEY)
    vectors = []
    batch_size = 64
    for i in range(0, len(texts), batch_size):
        response = client.embeddings.create(
            model=EMBED_MODEL,
            input=texts[i:i + batch_size],
            dimensions=dim,
        )
        vectors.extend(item.embedding for item in response.data)
    return vectors
