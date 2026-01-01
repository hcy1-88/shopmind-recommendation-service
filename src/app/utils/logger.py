"""
@File       : logger.py
@Description:

@Time       : 2025/12/31 23:01
@Author     : hcy18
"""
import logging
from datetime import datetime
from pathlib import Path

from app.utils.trace_context import get_trace_id

# 尝试使用 colorlog ( uv add colorlog )，如果没有安装则降级为普通 formatter
try:
    from colorlog import ColoredFormatter

    USE_COLOR = True
except ImportError:
    USE_COLOR = False


class TraceIDFilter(logging.Filter):
    """日志过滤器：自动注入 traceId 到日志记录中."""

    def filter(self, record: logging.LogRecord) -> bool:
        """
        为日志记录添加 traceId.

        Args:
            record: 日志记录对象

        Returns:
            True，表示不过滤该记录
        """
        record.traceId = get_trace_id()
        return True


def setup_logging(
        log_level: int = logging.INFO,
        log_dir: str = "logs",
        console_color: bool = True,
) -> logging.Logger:
    """
    初始化日志系统。

    Args:
        log_level: 日志级别，默认 INFO
        log_dir: 日志文件存储目录（相对于项目根目录）
        console_color: 是否启用控制台彩色输出（需安装 colorlog）

    Returns:
        配置好的 logger 实例（通常不需要使用返回值）
    """
    log_file_path = Path(__file__).resolve()  # 文件当前所在目录
    project_root = log_file_path.parent  # 当前目录的父目录
    # 向上查找到含 pyproject.toml 的目录，也就是项目根目录
    while project_root != project_root.parent:
        if (project_root / "pyproject.toml").exists():
            break
        project_root = project_root.parent

    # 创建日志目录
    log_dir_path = project_root / log_dir
    log_dir_path.mkdir(exist_ok=True)

    # 日志文件路径（按天分割）
    log_file = log_dir_path / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    # 创建格式器
    file_formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    if console_color and USE_COLOR:
        console_formatter = ColoredFormatter(
            fmt='%(log_color)s%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'white',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
    else:
        console_formatter = file_formatter

    # 获取 root logger 并清理已有 handler（防止重复）
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除已有 handlers（避免重复日志）
    if root_logger.handlers:
        root_logger.handlers.clear()

    # 过滤器
    trace_filter = TraceIDFilter()

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(trace_filter)
    root_logger.addHandler(console_handler)

    # 文件 handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(trace_filter)
    root_logger.addHandler(file_handler)

    return root_logger

app_logger = logging.getLogger(__name__)