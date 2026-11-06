import os
from dotenv import load_dotenv

load_dotenv()

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 大模型配置
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")
GLM_MODEL = "glm-4-flash"  # 生成模型
EMBED_MODEL = "embedding-3"  # 向量模型
# 数据路径（相对路径按项目根目录解析）
_data_dir = os.getenv("DATA_DIR", "data")
DATA_DIR = os.path.join(BASE_DIR, _data_dir)
# 向量库路径
MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
DIM = 1024
DB_NAME = "rag_db"
COLLECTION_NAME = "rag_collection"
# 上传文档保存目录
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

# 上传文件大小限制（MB）
MAX_UPLOAD_MB = 20

# 会话过期时间（秒）
SESSION_TTL = 3600
