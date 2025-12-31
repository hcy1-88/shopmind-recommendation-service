"""
@File       : trace_middleware.py
@Description:

@Time       : 2025/12/31 23:58
@Author     : hcy18
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.utils.trace_context import extract_trace_id_from_request, set_trace_id


class TraceIDMiddleware(BaseHTTPMiddleware):
    """中间件：从请求头提取 traceId 并设置到上下文变量中."""

    async def dispatch(self, request: Request, call_next):
        """
        处理请求，提取 traceId 并设置到上下文.

        Args:
            request: FastAPI Request 对象
            call_next: 下一个中间件或路由处理函数

        Returns:
            响应对象
        """
        # 从请求头提取 traceId
        trace_id = extract_trace_id_from_request(request)

        # 设置到上下文变量
        set_trace_id(trace_id)

        # 继续处理请求
        response = await call_next(request)

        # 将 traceId 添加到响应头
        response.headers["X-Trace-ID"] = trace_id

        return response
