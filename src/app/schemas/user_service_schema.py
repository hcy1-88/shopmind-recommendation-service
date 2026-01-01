"""
@File       : user_service_schema.py
@Description: ==================== 用户服务相关模型 ====================

@Time       : 2026/1/1 17:40
@Author     : hcy18
"""
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field

from app.schemas.base import CamelCaseModel


class UserInterestsResponseDTO(CamelCaseModel):
    """用户兴趣响应 DTO."""
    user_id: int = Field(..., description="用户ID")
    interests: dict[str, str] = Field(default_factory=dict, description="兴趣标签，key是英文code，value是中文名称")


BehaviorType = Literal["view", "like", "share", "search", "add_cart", "purchase"]
TargetType = Literal["product", "review", "order", "keyword"]

class UserBehaviorRequest(CamelCaseModel):
    """用户行为请求 DTO."""
    user_id: int = Field(..., description="用户ID")
    behavior_type: Optional[BehaviorType] = Field(None, description="行为类型")  # view/like/share/search/add_cart/purchase
    target_type: Optional[TargetType] = Field(None, description="目标类型")  # product/review/order/keyword
    day: int = Field(default=7, description="最近多少天")


class UserBehaviorResponseDTO(CamelCaseModel):
    """用户行为响应 DTO."""
    user_id: int = Field(..., description="用户ID")
    behavior_type: Optional[str] = Field(default=None, description="行为类型：view/like/share/search/add_cart/purchase")
    target_type: Optional[str] = Field(default=None, description="目标类型：product/review/order/keyword")
    target_id: Optional[int] = Field(default=None, description="目标ID")
    search_keyword: Optional[str] = Field(default=None, description="搜索关键词")
    created_at: Optional[datetime] = Field(default=None, description="行为发生时间")

