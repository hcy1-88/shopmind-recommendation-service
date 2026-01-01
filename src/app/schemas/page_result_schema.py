"""
@File       : page_result_schema.py
@Description:

@Time       : 2026/1/1 17:44
@Author     : hcy18
"""
from typing import TypeVar, Generic
from pydantic import Field
from app.schemas.base import CamelCaseModel

T = TypeVar("T")

class PageResult(CamelCaseModel, Generic[T]):
    """分页结果."""
    data: T = Field(..., description="分页数据")
    total: int = Field(..., description="总记录数")
    page_number: int = Field(..., description="当前页码")
    page_size: int = Field(...,  description="每页大小")

