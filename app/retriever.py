"""向量检索与文档管理（简化版：仅向量检索）"""
from pymilvus import DataType, MilvusClient

from app.config import COLLECTION_NAME, DB_NAME, DIM, MILVUS_URI
from app.data_loader import embed_texts

milvus = MilvusClient(MILVUS_URI)


def ensure_collection(reset: bool = False):
    if DB_NAME not in milvus.list_databases():
        milvus.create_database(DB_NAME)
    milvus.use_database(DB_NAME)
    if milvus.has_collection(COLLECTION_NAME):
        fields = [f["name"] for f in milvus.describe_collection(COLLECTION_NAME)["fields"]]
        if "doc_id" in fields and not reset:
            return
        milvus.drop_collection(COLLECTION_NAME)
    schema = milvus.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("doc_id", DataType.VARCHAR, max_length=64)
    schema.add_field("content", DataType.VARCHAR, max_length=65535)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=DIM)
    index_params = milvus.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
    milvus.create_collection(collection_name=COLLECTION_NAME, schema=schema, index_params=index_params)


def add_document(doc_id: str, chunks: list):
    """文档切片向量化入库"""
    vectors = embed_texts(chunks, DIM)
    rows = [{"doc_id": doc_id, "content": c, "vector": v} for c, v in zip(chunks, vectors)]
    ensure_collection()
    milvus.insert(collection_name=COLLECTION_NAME, data=rows)


def delete_document(doc_id: str):
    """删除指定文档的所有向量"""
    ensure_collection()
    milvus.delete(collection_name=COLLECTION_NAME, filter='doc_id == "%s"' % doc_id)


def list_documents() -> list:
    """按 doc_id 汇总文档列表和切片数"""
    rows = milvus.query(collection_name=COLLECTION_NAME, filter="id >= 0", output_fields=["doc_id"])
    stats = {}
    for r in rows:
        stats[r["doc_id"]] = stats.get(r["doc_id"], 0) + 1
    return [{"doc_id": k, "chunk_count": v} for k, v in stats.items()]


def search(query: str, top_k: int = 5) -> list:
    """向量检索，返回相关片段"""
    query_vector = embed_texts([query], DIM)[0]
    results = milvus.search(
        collection_name=COLLECTION_NAME,
        data=[query_vector],
        limit=top_k,
        output_fields=["doc_id", "content"],
        search_params={"metric_type": "COSINE"},
    )
    return [{"doc_id": h["entity"]["doc_id"], "content": h["entity"]["content"],
             "score": 1.0 - h["distance"]} for h in results[0]]
