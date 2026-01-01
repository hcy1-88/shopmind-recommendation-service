"""
@File       : product_service_schema.py
@Description: ==================== 商品服务相关模型 ====================

@Time       : 2026/1/1 17:41
@Author     : hcy18
"""
from decimal import Decimal
from typing import Optional, List
from pydantic import Field
from app.schemas.base import CamelCaseModel


class PriceRange(CamelCaseModel):
    """价格范围."""
    min: Optional[Decimal] = Field(None, description="最低价格")
    max: Optional[Decimal] = Field(None, description="最高价格")


class TagInfo(CamelCaseModel):
    """标签信息."""
    name: str = Field(..., description="标签名称")
    type: Optional[str] = Field(None, description="标签类型")


class ProductResponseDto(CamelCaseModel):
    """商品响应 DTO（与 Java 服务保持一致）."""
    id: int = Field(..., description="商品ID")
    name: str = Field(..., description="商品名称")
    price: Decimal = Field(..., description="价格")
    original_price: Optional[Decimal] = Field(None, description="原价")
    price_range: Optional[PriceRange] = Field(None, description="价格范围")
    image: str = Field(..., description="预览图/封面")
    images: List[str] = Field(default_factory=list, description="详情图列表")
    ai_summary: Optional[str] = Field(None, description="商品摘要（AI生成）")
    description: str = Field(..., description="商品描述")
    location: Optional[str] = Field(None, description="位置")
    category: int = Field(..., description="分类ID")
    tag_info: List[TagInfo] = Field(default_factory=list, description="商品标签")
    sales_count: int = Field(default=0, description="销量")

    class Config:
        populate_by_name = True


class ProductGettingRequestDTO(CamelCaseModel):
    """批量获取商品请求 DTO."""
    ids: List[int] = Field(..., description="商品ID列表")
