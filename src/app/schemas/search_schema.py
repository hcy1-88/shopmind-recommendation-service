"""
@File       : search_schema.py
@Description: ==================== 搜索服务相关模型 ====================

@Time       : 2026/1/1 17:43
@Author     : hcy18
"""
from typing import Optional

from app.decorators.deprecation_decorator import deprecated
from pydantic import Field
from app.schemas.base import CamelCaseModel


@deprecated("搜索功能弃用，由商品服务实现和协调")
class ProductSearchParams(CamelCaseModel):
    """商品搜索请求参数."""
    keyword: str = Field(..., min_length=1, description="搜索关键词")
    page_number: int = Field(default=1, ge=1, description="页码，从1开始")
    page_size: int = Field(default=10, ge=1, le=100, description="每页大小，1-100")



class ProductSemanticSearchRequest(CamelCaseModel):
    """纯语义搜索"""
    keyword: str = Field(..., description="搜索关键词")
    limit: int = Field(..., description="返回 limit 个")
    product_ids: Optional[list[int]] = Field(default=None, description="商品 id 过滤，即在这些商品里搜索")


