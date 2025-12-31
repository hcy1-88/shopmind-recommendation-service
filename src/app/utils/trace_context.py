"""
@File       : trace_context.py
@Description:

@Time       : 2025/12/31 23:58
@Author     : hcy18
"""
"""Trace ID context management using contextvars."""

import contextvars
import uuid
from typing import Optional

from fastapi import Request

# 固定的 traceId 请求头名称
TRACE_ID_HEADER = "X-Trace-ID"

# 创建上下文变量
trace_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)


def get_trace_id() -> str:
    """
    从上下文变量中获取当前请求的 traceId.

    如果上下文中没有，则生成新的 UUID。

    Returns:
        链路追踪ID
    """
    trace_id = trace_id_context.get()
    if trace_id:
        return trace_id
    return str(uuid.uuid4())


def set_trace_id(trace_id: str) -> None:
    """
    设置 traceId 到上下文变量.

    Args:
        trace_id: 链路追踪ID
    """
    trace_id_context.set(trace_id)


def extract_trace_id_from_request(request: Request) -> str:
    """
    从请求头中提取 traceId，如果不存在则生成新的.

    Args:
        request: FastAPI Request 对象

    Returns:
        链路追踪ID
    """
    trace_id = request.headers.get(TRACE_ID_HEADER)
    if trace_id:
        return trace_id
    return str(uuid.uuid4())

