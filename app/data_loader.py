"""文档解析与向量化：API 上传流程使用"""
from langchain_community.document_loaders import UnstructuredWordDocumentLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from zai import ZhipuAiClient

from app.config import EMBED_MODEL, ZHIPU_API_KEY

_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=100,
    chunk_overlap=20,
    separators=["\n\n", "\n", "，", "。", ""],
)


def parse_file(file_path: str) -> list[str]:
    """解析单个上传的文档并切分，返回文本块列表"""
    if file_path.endswith(".docx"):
        loader = UnstructuredWordDocumentLoader(file_path)
    elif file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    else:
        raise ValueError(f"不支持的文件类型: {file_path}")
    return [c.page_content for c in _SPLITTER.split_documents(loader.load())]


def embed_texts(texts: list[str], dim: int = 1024) -> list[list[float]]:
    """批量向量化（embedding 接口单次最多 64 条）"""
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
