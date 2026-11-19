"""LangChain Milvus 向量库生命周期和文档操作。"""
from contextlib import asynccontextmanager
import re
from typing import Any, AsyncIterator

class ZhipuEmbeddings:
    """将现有智谱 embedding 接口适配到 LangChain Embeddings 契约。"""

    def __init__(self, dim: int):
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        from app.modules.document.splitter import embed_texts

        return embed_texts(texts, self.dim)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def create_milvus_store(uri: str, db_name: str, collection_name: str, dim: int) -> Any:
    """创建 LangChain Milvus store；collection 在首次写入时自动生成。"""
    from langchain_milvus import BM25BuiltInFunction, Milvus

    return Milvus(
        embedding_function=ZhipuEmbeddings(dim),
        collection_name=collection_name,
        connection_args={"uri": uri, "db_name": db_name},
        enable_dynamic_field=True,
        drop_old=False,
        builtin_function=BM25BuiltInFunction(analyzer_params={"type": "chinese"}),
        vector_field=["dense", "sparse"],
    )


@asynccontextmanager
async def milvus_lifespan(
    app: Any,
    uri: str,
    db_name: str,
    collection_name: str,
    dim: int,
) -> AsyncIterator[Any]:
    """在应用运行期间持有 LangChain store，并在退出时释放连接。"""
    store = create_milvus_store(uri, db_name, collection_name, dim)
    app.state.milvus = store
    try:
        yield store
    finally:
        del app.state.milvus


def add_document(store: Any, doc_id: str, chunks: list[dict]) -> None:
    """把子块转成 LangChain Document，并由 vector store 自动建 collection。"""
    from langchain_core.documents import Document

    documents = []
    for chunk in chunks:
        metadata = dict(chunk.get("metadata", {}))
        metadata["doc_id"] = doc_id
        if not metadata.get("parent_id"):
            raise ValueError("子块缺少 parent_id")
        documents.append(Document(page_content=chunk["content"], metadata=metadata))
    store.add_documents(documents=documents)


def delete_document(store: Any, doc_id: str) -> None:
    """按动态 metadata 中的 doc_id 删除其全部子块。"""
    if not re.fullmatch(r"[a-f0-9]{12}", doc_id):
        raise ValueError("无效的 doc_id")
    if store.col is None:
        return
    store.delete(expr=f'doc_id == "{doc_id}"')


def search(store: Any, query: str, top_k: int = 5) -> list[dict]:
    """在 Milvus 混合检索子块时使用 SiliconFlow 模型重排。"""
    if store.col is None:
        return []

    from pymilvus import Function, FunctionType

    # LangChain 的正文默认字段是 text；Milvus 在返回子块前调用模型重排该字段。
    ranker = Function(
        name="siliconflow_semantic_ranker",
        input_field_names=["text"],
        function_type=FunctionType.RERANK,
        params={
            "reranker": "model",
            "provider": "siliconflow",
            "model_name": "BAAI/bge-reranker-v2-m3",
            "queries": [query],
            # credential 是 Milvus 中的凭据名称；省略后读取服务端环境变量。
        },
    )
    results = store.similarity_search_with_score(
        query, k=top_k, fetch_k=max(top_k * 2, 10), reranker=ranker
    )
    fields = (
        "title", "article_no", "chapter", "page", "source_file",
        "effective_date", "status", "part_no",
    )
    return [
        {
            "doc_id": document.metadata["doc_id"],
            "parent_id": document.metadata["parent_id"],
            "child_index": document.metadata.get("child_index"),
            "content": document.page_content,
            "score": score,
            **{key: document.metadata.get(key) for key in fields},
        }
        for document, score in results
    ]
