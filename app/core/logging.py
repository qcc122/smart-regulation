"""控制台日志着色，并在输出前遮蔽已配置的凭据。"""
import logging
import sys
from collections.abc import Iterable
from typing import TextIO


_RESET = "\x1b[0m"
_LEVEL_COLORS = {
    logging.DEBUG: "\x1b[36m",
    logging.INFO: "\x1b[32m",
    logging.WARNING: "\x1b[33m",
    logging.ERROR: "\x1b[31m",
    logging.CRITICAL: "\x1b[35;1m",
}


class ColorFormatter(logging.Formatter):
    """终端支持颜色时按等级着色；重定向输出保持纯文本。"""
    def __init__(self, fmt: str, *, use_color: bool | None = None):
        super().__init__(fmt)
        self.use_color = sys.stderr.isatty() if use_color is None else use_color

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        color = _LEVEL_COLORS.get(record.levelno)
        if not self.use_color or color is None:
            return message
        return f"{color}{message}{_RESET}"


class SecretRedactionFilter(logging.Filter):
    """同时处理普通日志参数和异常堆栈，避免凭据随日志输出。"""
    def __init__(self, secrets: Iterable[str]):
        super().__init__()
        self.secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg = message
        record.args = ()
        if record.exc_info:
            traceback_text = logging.Formatter().formatException(record.exc_info)
            for secret in self.secrets:
                traceback_text = traceback_text.replace(secret, "[REDACTED]")
            record.exc_text = traceback_text
        return True


def configure_logging(
    *,
    logger: logging.Logger | None = None,
    level: int = logging.INFO,
    stream: TextIO | None = None,
    secrets: Iterable[str] = (),
) -> None:
    """安装控制台 formatter 和凭据过滤器，重复调用不会叠加本模块的 handler。"""
    target = logger or logging.getLogger()
    output = stream or sys.stderr
    handler = logging.StreamHandler(output)
    handler.setFormatter(ColorFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(SecretRedactionFilter(secrets))

    # 只替换本模块此前创建的 handler，保留 Uvicorn 或测试框架安装的 handler。
    for old_handler in target.handlers[:]:
        if getattr(old_handler, "_smart_regulation_console", False):
            target.removeHandler(old_handler)
            old_handler.close()
    handler._smart_regulation_console = True
    target.addHandler(handler)
    target.setLevel(level)
