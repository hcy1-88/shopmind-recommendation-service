"""
@File       : recommendation_schema.py
@Description: Recommendation related data models

@Time       : 2026/01/01
@Author     : hcy18
"""
from typing import List
from pydantic import BaseModel, Field

from app.schemas.base import CamelCaseModel
from app.schemas.product_service_schema import ProductResponseDto


# ==================== 推荐服务相关模型 ====================

class RecommendationRequest(CamelCaseModel):
    """推荐请求."""
    user_id: int = Field(..., description="用户ID")
    limit: int = Field(default=10, ge=1, le=100, description="推荐数量，1-100")


class RecommendationResponse(CamelCaseModel):
    """推荐响应."""
    products: List[ProductResponseDto] = Field(..., description="推荐的商品列表")
    strategy: str = Field(..., description="推荐策略：personalized/cold_start/fallback")
    total: int = Field(..., description="推荐商品总数")





