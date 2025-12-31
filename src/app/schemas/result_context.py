"""
@File       : result_context.py
@Description:

@Time       : 2025/12/31 23:59
@Author     : hcy18
"""
"""统一接口返回类型 ResultContext."""

from typing import Generic, TypeVar, Optional, Dict, Any

from pydantic import Field

from app.schemas.base import CamelCaseModel

from app.utils.trace_context import get_trace_id

T = TypeVar("T")

# 常量定义
SUCCESS_CODE = "0"
SYSTEM_ERROR_CODE = "SYS9999"


class ResultContext(CamelCaseModel, Generic[T]):
    """
    统一接口返回类型.

    与 Java 微服务的 ResultContext 保持一致。
    """

    # 返回数据
    data: Optional[T] = Field(default=None, description="返回数据")

    # 是否成功
    success: bool = Field(..., description="是否成功")

    # 状态码
    code: str = Field(..., description="状态码")

    # 消息
    message: str = Field(..., description="消息")

    # 链路追踪ID
    trace_id: str = Field(default_factory=get_trace_id, description="链路追踪ID")

    # 额外信息，用于向后兼容
    extra: Dict[str, Any] = Field(default_factory=dict, description="额外信息")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "success": True,
                    "code": "0",
                    "message": "操作成功",
                    "data": {"valid": True},
                    "traceId": "123e4567-e89b-12d3-a456-426614174000",
                    "extra": {},
                },
                {
                    "success": False,
                    "code": "SYS9999",
                    "message": "操作失败",
                    "data": None,
                    "traceId": "123e4567-e89b-12d3-a456-426614174000",
                    "extra": {},
                },
            ],
        }

    # ==================== 静态工厂方法 ====================

    @staticmethod
    def ok(
        data: Optional[T] = None,
        message: str = "操作成功",
        trace_id: Optional[str] = None,
    ) -> "ResultContext[T]":
        """
        成功返回.

        Args:
            data: 返回数据
            message: 消息
            trace_id: 链路追踪ID（可选）

        Returns:
            ResultContext 实例
        """
        return ResultContext(
            success=True,
            code=SUCCESS_CODE,
            message=message,
            data=data,
            trace_id=trace_id if trace_id else get_trace_id(),
        )

    @staticmethod
    def fail(
        message: str = "操作失败",
        code: str = SYSTEM_ERROR_CODE,
        data: Optional[T] = None,
        trace_id: Optional[str] = None,
    ) -> "ResultContext[T]":
        """
        失败返回.

        Args:
            message: 消息
            code: 状态码
            data: 返回数据
            trace_id: 链路追踪ID（可选）

        Returns:
            ResultContext 实例
        """
        return ResultContext(
            success=False,
            code=code,
            message=message,
            data=data,
            trace_id=trace_id if trace_id else get_trace_id(),
        )

    # ==================== Builder 构建者模式 ====================

    @staticmethod
    def success_builder() -> "ResultContextBuilder[T]":
        """开始构建成功响应."""
        return ResultContextBuilder[T]().success(True).code(SUCCESS_CODE).message("操作成功")

    @staticmethod
    def fail_builder() -> "ResultContextBuilder[T]":
        """开始构建失败响应."""
        return ResultContextBuilder[T]().success(False).code(SYSTEM_ERROR_CODE).message("操作失败")

    @staticmethod
    def builder() -> "ResultContextBuilder[T]":
        """自定义构建."""
        return ResultContextBuilder[T]()


class ResultContextBuilder(Generic[T]):
    """ResultContext 构建者."""

    def __init__(self):
        self._data: Optional[T] = None
        self._success: Optional[bool] = None
        self._code: Optional[str] = None
        self._message: Optional[str] = None
        self._trace_id: Optional[str] = None
        self._extra: Dict[str, Any] = {}

    def data(self, data: T) -> "ResultContextBuilder[T]":
        """设置数据."""
        self._data = data
        return self

    def success(self, success: bool) -> "ResultContextBuilder[T]":
        """设置成功标志."""
        self._success = success
        return self

    def code(self, code: str) -> "ResultContextBuilder[T]":
        """设置状态码."""
        self._code = code
        return self

    def message(self, message: str) -> "ResultContextBuilder[T]":
        """设置消息."""
        self._message = message
        return self

    def trace_id(self, trace_id: str) -> "ResultContextBuilder[T]":
        """设置链路追踪ID."""
        self._trace_id = trace_id
        return self

    def extra(self, extra: Dict[str, Any]) -> "ResultContextBuilder[T]":
        """设置额外信息."""
        self._extra = extra
        return self

    def put_extra(self, key: str, value: Any) -> "ResultContextBuilder[T]":
        """添加额外信息."""
        self._extra[key] = value
        return self

    def build(self) -> ResultContext[T]:
        """构建 ResultContext 实例."""
        return ResultContext(
            data=self._data,
            success=self._success if self._success is not None else False,
            code=self._code if self._code is not None else SYSTEM_ERROR_CODE,
            message=self._message if self._message is not None else "操作失败",
            trace_id=self._trace_id if self._trace_id is not None else get_trace_id(),
            extra=self._extra,
        )

