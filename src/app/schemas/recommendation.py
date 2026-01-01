"""
@File       : recommendation.py
@Description: Recommendation related data models

@Time       : 2026/01/01
@Author     : hcy18
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ==================== 用户服务相关模型 ====================

class UserInterestsResponseDTO(BaseModel):
    """用户兴趣响应 DTO."""
    user_id: int = Field(..., alias="userId", description="用户ID")
    interests: Dict[str, str] = Field(default_factory=dict, description="兴趣标签，key是英文code，value是中文名称")

    class Config:
        populate_by_name = True


class UserBehaviorRequest(BaseModel):
    """用户行为请求 DTO."""
    user_id: int = Field(..., alias="userId", description="用户ID")
    behavior_type: Optional[str] = Field(None, alias="behaviorType", description="行为类型")
    target_type: Optional[str] = Field(None, alias="targetType", description="目标类型")
    day: int = Field(default=7, description="最近多少天")

    class Config:
        populate_by_name = True


class UserBehaviorResponseDTO(BaseModel):
    """用户行为响应 DTO."""
    user_id: int = Field(..., alias="userId", description="用户ID")
    behavior_type: str = Field(..., alias="behaviorType", description="行为类型：view/like/share/search/add_cart/purchase")
    target_type: str = Field(..., alias="targetType", description="目标类型：product/review/order/keyword")
    target_id: str = Field(..., alias="targetId", description="目标ID")
    search_keyword: Optional[str] = Field(None, alias="searchKeyword", description="搜索关键词")
    created_at: datetime = Field(..., alias="createdAt", description="行为发生时间")

    class Config:
        populate_by_name = True


# ==================== 商品服务相关模型 ====================

class PriceRange(BaseModel):
    """价格范围."""
    min: Optional[Decimal] = Field(None, description="最低价格")
    max: Optional[Decimal] = Field(None, description="最高价格")


class TagInfo(BaseModel):
    """标签信息."""
    name: str = Field(..., description="标签名称")
    type: Optional[str] = Field(None, description="标签类型")


class ProductResponseDto(BaseModel):
    """商品响应 DTO（与 Java 服务保持一致）."""
    id: int = Field(..., description="商品ID")
    name: str = Field(..., description="商品名称")
    price: Decimal = Field(..., description="价格")
    original_price: Optional[Decimal] = Field(None, alias="originalPrice", description="原价")
    price_range: Optional[PriceRange] = Field(None, alias="priceRange", description="价格范围")
    image: str = Field(..., description="预览图/封面")
    images: List[str] = Field(default_factory=list, description="详情图列表")
    ai_summary: Optional[str] = Field(None, alias="aiSummary", description="商品摘要（AI生成）")
    description: str = Field(..., description="商品描述")
    location: Optional[str] = Field(None, description="位置")
    category: int = Field(..., description="分类ID")
    tag_info: List[TagInfo] = Field(default_factory=list, alias="tagInfo", description="商品标签")
    sales_count: int = Field(default=0, alias="salesCount", description="销量")

    class Config:
        populate_by_name = True


class ProductGettingRequestDTO(BaseModel):
    """批量获取商品请求 DTO."""
    ids: List[int] = Field(..., description="商品ID列表")


# ==================== 推荐服务相关模型 ====================

class RecommendationRequest(BaseModel):
    """推荐请求."""
    user_id: int = Field(..., description="用户ID")
    limit: int = Field(default=10, ge=1, le=100, description="推荐数量，1-100")


class RecommendationResponse(BaseModel):
    """推荐响应."""
    products: List[ProductResponseDto] = Field(..., description="推荐的商品列表")
    strategy: str = Field(..., description="推荐策略：personalized/cold_start/fallback")
    total: int = Field(..., description="推荐商品总数")


# ==================== 搜索服务相关模型 ====================

class ProductSearchParams(BaseModel):
    """商品搜索请求参数."""
    keyword: str = Field(..., min_length=1, description="搜索关键词")
    page_number: int = Field(default=1, ge=1, alias="pageNumber", description="页码，从1开始")
    page_size: int = Field(default=10, ge=1, le=100, alias="pageSize", description="每页大小，1-100")

    class Config:
        populate_by_name = True


class PageResult(BaseModel):
    """分页结果."""
    data: List[ProductResponseDto] = Field(..., description="分页数据")
    total: int = Field(..., description="总记录数")
    page_number: int = Field(..., alias="pageNumber", description="当前页码")
    page_size: int = Field(..., alias="pageSize", description="每页大小")

    class Config:
        populate_by_name = True

