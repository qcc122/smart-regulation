"""通过 MinerU Open API 将 PDF/DOCX 提取为 Markdown。"""
import logging
from pathlib import Path

import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DocumentParseError(ValueError):
    """文档不支持、无内容或 MinerU API 解析失败。"""


def _extract_with_mineru(path: Path, token: str) -> str:
    """使用课程示例中的 MinerU 客户端，读取 extract 结果的 Markdown。"""
    from mineru import MinerU

    # SDK 自行管理 HTTP 请求；上下文退出时关闭客户端连接。
    with MinerU(token) as client:
        result = client.extract(str(path))
        return result.markdown


def parse_document(path: str | Path, source_file: str | None = None) -> str:
    """校验上传文件并返回 MinerU 提取的 Markdown 原文。"""
    file_path = Path(path)
    source_type = file_path.suffix.lower()
    if source_type not in {".pdf", ".docx"}:
        raise DocumentParseError("仅支持 PDF/DOCX 文件")
    if not file_path.is_file():
        raise DocumentParseError(f"源文件不存在：{file_path.name}")
    if file_path.stat().st_size == 0:
        raise DocumentParseError(f"源文件为空：{file_path.name}")

    # 用户端可能传入浏览器伪路径；日志中只保留文件名。
    safe_source_file = str(source_file or file_path.name).replace("\\", "/").rsplit("/", 1)[-1]
    token = get_settings().mineru_token
    if token is None or not token.get_secret_value().strip():
        raise DocumentParseError("未配置 MinerU API Token（MINERU_TOKEN）")

    try:
        markdown = _extract_with_mineru(file_path, token.get_secret_value())
    except Exception as exc:
        # 错误响应不带回 SDK 异常详情，避免把请求信息或凭据暴露给调用方。
        target_host = exc.request.url.host if isinstance(exc, httpx.RequestError) else "unknown"
        logger.error(
            "MinerU API 解析失败 source_file=%s error_type=%s target_host=%s",
            safe_source_file,
            type(exc).__name__,
            target_host,
        )
        raise DocumentParseError(f"MinerU 解析失败：{safe_source_file}") from None

    if not isinstance(markdown, str) or not markdown.strip():
        raise DocumentParseError(f"MinerU 未提取到 Markdown：{safe_source_file}")
    return markdown
