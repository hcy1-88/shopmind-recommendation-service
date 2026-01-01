"""
@File       : search_schema.py
@Description: ==================== 搜索服务相关模型 ====================

@Time       : 2026/1/1 17:43
@Author     : hcy18
"""
from pydantic import Field

from app.schemas.base import CamelCaseModel


class ProductSearchParams(CamelCaseModel):
    """商品搜索请求参数."""
    keyword: str = Field(..., min_length=1, description="搜索关键词")
    page_number: int = Field(default=1, ge=1, description="页码，从1开始")
    page_size: int = Field(default=10, ge=1, le=100, description="每页大小，1-100")

