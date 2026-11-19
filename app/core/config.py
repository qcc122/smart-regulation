"""应用配置，并暂时保留现有模块使用的常量名。"""
import os
from pathlib import Path
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import ConfigurationError


class RagSettings(BaseModel):
    """模型服务、Milvus 与 RAG 参数的分组视图。"""
    zhipu_api_key: SecretStr | None
    zhipu_base_url: str
    zhipu_embedding_url: str
    glm_model: str
    embed_model: str
    siliconflow_api_key: SecretStr | None
    milvus_uri: str
    milvus_db_name: str
    milvus_collection_name: str
    vector_dim: int
    mineru_token: SecretStr | None


class DbSettings(BaseModel):
    """PostgreSQL 连接参数的分组视图。"""
    host: str
    port: int
    name: str
    user: str
    password: SecretStr | None


class Settings(BaseSettings):
    """从扁平环境变量加载配置，并提供按用途分组的视图。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 密钥使用 SecretStr，避免配置对象被日志或调试输出时意外暴露明文。
    zhipu_api_key: SecretStr | None = Field(default=None, validation_alias="ZHIPU_API_KEY")
    zhipu_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4/",
        validation_alias="ZHIPU_BASE_URL",
    )
    zhipu_embedding_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4/embeddings",
        validation_alias="ZHIPU_EMBEDDING_URL",
    )
    glm_model: str = Field(default="glm-4-flash", validation_alias="GLM_MODEL")
    embed_model: str = Field(default="embedding-3", validation_alias="EMBED_MODEL")
    siliconflow_api_key: SecretStr | None = Field(default=None, validation_alias="SILICONFLOW_API_KEY")

    milvus_uri: str = Field(default="http://localhost:19530", validation_alias="MILVUS_URI")
    milvus_db_name: str = Field(default="default", validation_alias="DB_NAME")
    milvus_collection_name: str = Field(default="rag_collection", validation_alias="COLLECTION_NAME")
    vector_dim: int = Field(default=1024, gt=0, validation_alias="DIM")
    mineru_token: SecretStr | None = Field(default=None, validation_alias="MINERU_TOKEN")

    postgres_host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, gt=0, le=65535, validation_alias="POSTGRES_PORT")
    postgres_db: str = Field(default="smart_regulation", validation_alias="POSTGRES_DB")
    postgres_user: str = Field(default="regulation_app", validation_alias="POSTGRES_USER")
    postgres_password: SecretStr | None = Field(default=None, validation_alias="POSTGRES_PASSWORD")

    data_dir: str = Field(default="data", validation_alias="DATA_DIR")
    max_upload_mb: int = Field(default=20, gt=0, validation_alias="MAX_UPLOAD_MB")

    @property
    def rag(self) -> RagSettings:
        """将模型、Milvus 与文档解析配置集中交给 RAG 服务。"""
        return RagSettings(
            zhipu_api_key=self.zhipu_api_key,
            zhipu_base_url=self.zhipu_base_url,
            zhipu_embedding_url=self.zhipu_embedding_url,
            glm_model=self.glm_model,
            embed_model=self.embed_model,
            siliconflow_api_key=self.siliconflow_api_key,
            milvus_uri=self.milvus_uri,
            milvus_db_name=self.milvus_db_name,
            milvus_collection_name=self.milvus_collection_name,
            vector_dim=self.vector_dim,
            mineru_token=self.mineru_token,
        )

    @property
    def db(self) -> DbSettings:
        """把扁平环境变量映射成数据库连接所需的配置对象。"""
        return DbSettings(
            host=self.postgres_host,
            port=self.postgres_port,
            name=self.postgres_db,
            user=self.postgres_user,
            password=self.postgres_password,
        )

    def validate_required(self) -> "Settings":
        # 只列出缺失字段名，不把用户输入的凭据放进异常文本。
        missing = []
        for env_name, value in (
            ("ZHIPU_API_KEY", self.zhipu_api_key),
            ("POSTGRES_PASSWORD", self.postgres_password),
            ("MINERU_TOKEN", self.mineru_token),
            ("SILICONFLOW_API_KEY", self.siliconflow_api_key),
        ):
            if value is None or not value.get_secret_value().strip():
                missing.append(env_name)
        if missing:
            raise ConfigurationError("Missing required settings: " + ", ".join(missing))
        return self


def get_settings() -> Settings:
    """重新读取环境配置，供启动检查及需要新配置的服务使用。"""
    # 启动时读取最新环境变量；模块级兼容常量仅供尚未迁移的旧代码使用。
    return Settings()


BASE_DIR = str(Path(__file__).resolve().parent.parent)
_settings = Settings()
_data_dir = Path(_settings.data_dir)
DATA_DIR = str(_data_dir if _data_dir.is_absolute() else Path(BASE_DIR) / _data_dir)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

# 迁移现有路由和数据模块前，保留它们当前使用的配置常量名。
ZHIPU_API_KEY = (
    _settings.zhipu_api_key.get_secret_value() if _settings.zhipu_api_key is not None else None
)
GLM_MODEL = _settings.glm_model
EMBED_MODEL = _settings.embed_model
MILVUS_URI = _settings.milvus_uri
DIM = _settings.vector_dim
DB_NAME = _settings.milvus_db_name
COLLECTION_NAME = _settings.milvus_collection_name
MAX_UPLOAD_MB = _settings.max_upload_mb
