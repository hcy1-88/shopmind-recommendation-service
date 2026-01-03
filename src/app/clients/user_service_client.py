"""
@File       : user_service_client.py
@Description: Client for calling user service APIs

@Time       : 2026/01/01
@Author     : hcy18
"""
from typing import List, Optional, Dict
import httpx
from fastapi import HTTPException

from app.clients.service_discovery import get_user_service_url
from app.schemas.user_service_schema import UserInterestsResponseDTO, UserBehaviorRequest, UserBehaviorResponseDTO
from app.schemas.result_context import ResultContext
from app.utils.logger import app_logger as logger
from app.utils.trace_context import get_trace_id, TRACE_ID_HEADER


class UserServiceClient:
    """用户服务客户端."""

    def __init__(self):
        self._base_url: Optional[str] = None
        self.timeout = 10.0  # 请求超时时间（秒）

    async def _get_base_url(self) -> str:
        """获取用户服务的基础 URL（带缓存）."""
        if not self._base_url:
            self._base_url = await get_user_service_url()
        return self._base_url

    def _get_headers(self) -> Dict[str, str]:
        """获取带 Trace ID 的请求头."""
        trace_id = get_trace_id()
        return {
            TRACE_ID_HEADER: trace_id,
            "Content-Type": "application/json"
        }

    async def get_user_interests(self, user_id: int) -> Optional[UserInterestsResponseDTO]:
        """
        获取用户兴趣标签.

        Args:
            user_id: 用户ID

        Returns:
            用户兴趣DTO，如果失败返回 None
        """
        try:
            base_url = await self._get_base_url()
            url = f"{base_url}/user/interests"
            headers = self._get_headers()

            logger.info(f"调用用户服务获取兴趣: user_id={user_id}, url={url}",)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params={"userId": user_id}, headers=headers)
                response.raise_for_status()

                # 解析 ResultContext 包裹的响应
                result_data = response.json()
                result = ResultContext[UserInterestsResponseDTO](**result_data)

                if result.success and result.data:
                    logger.info(
                        f"获取用户兴趣成功: user_id={user_id}, interests={result.data.interests}")
                    return result.data
                else:
                    logger.error(
                        f"获取用户兴趣失败: url={url}, user_id={user_id}, message={result.message}")
                    raise HTTPException(status_code=500, detail="获取用户兴趣失败")

        except httpx.TimeoutException:
            logger.error(f"获取用户兴趣超时: user_id={user_id}")
            raise
        except Exception as e:
            logger.error(
                f"获取用户兴趣异常: user_id={user_id}, error={str(e)}",
                exc_info=True
            )
            raise

    async def get_user_behaviors(
        self,
        user_id: int,
        day: int = 7,
        behavior_type: Optional[str] = None,
        target_type: Optional[str] = None
    ) -> List[UserBehaviorResponseDTO]:
        """
        获取用户行为历史.

        Args:
            user_id: 用户ID
            day: 最近多少天
            behavior_type: 行为类型（可选）
            target_type: 目标类型（可选，如 'product'）

        Returns:
            用户行为列表，如果失败返回空列表
        """
        try:
            base_url = await self._get_base_url()
            url = f"{base_url}/behavior/{user_id}"
            headers = self._get_headers()

            request_body = UserBehaviorRequest(
                user_id=user_id,
                day=day,
                behavior_type=behavior_type,
                target_type=target_type
            )

            logger.info(f"调用用户服务获取行为历史: user_id={user_id}, day={day}, target_type={target_type}",)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=request_body.model_dump(by_alias=True, exclude_none=True),
                    headers=headers
                )
                response.raise_for_status()
                jj = response.json()
                print(jj)
                behaviors_result_context = ResultContext[list[UserBehaviorResponseDTO]](**jj)
                if behaviors_result_context.success:
                    behaviors = behaviors_result_context.data
                    logger.info(f"获取用户行为历史成功: user_id={user_id}, count={len(behaviors)}")
                    return behaviors
                else:
                    logger.error(f"获取用户行为失败！url={url} , request={request_body.model_dump()}")
                    raise HTTPException(status_code=500, detail="用户服务获取用户行为异常！")
        except httpx.TimeoutException:
            logger.error(f"获取用户行为历史超时: user_id={user_id}")
            raise
        except Exception as e:
            logger.error(
                f"获取用户行为历史异常: user_id={user_id}, error={str(e)}",
                exc_info=True
            )
            raise

    async def get_product_behaviors(self, user_id: int, day: int = 30) -> List[int]:
        """
        获取用户最近的商品交互行为（仅返回商品ID列表）.

        Args:
            user_id: 用户ID
            day: 最近多少天

        Returns:
            商品ID列表（去重后）
        """
        behaviors = await self.get_user_behaviors(
            user_id=user_id,
            day=day,
            target_type="product"
        )

        # 提取商品ID并去重
        product_ids = []
        seen = set()
        for behavior in behaviors:
            if not behavior.target_id:
                continue
            else:
                product_id = int(behavior.target_id)
                if product_id not in seen:
                    product_ids.append(product_id)
                    seen.add(product_id)

        logger.info(f"提取用户商品行为: user_id={user_id}, product_count={len(product_ids)}")
        return product_ids

    async def get_purchased_products(self, user_id: int, day: int = 365) -> List[int]:
        """
        获取用户已购买的商品ID列表（用于推荐过滤）.

        Args:
            user_id: 用户ID
            day: 最近多少天（默认一年内）

        Returns:
            已购买的商品ID列表（去重后）
        """
        try:
            behaviors = await self.get_user_behaviors(
                user_id=user_id,
                day=day,
                behavior_type="purchase"
            )

            # 提取已购买的商品ID并去重
            purchased_ids = []
            seen = set()
            for behavior in behaviors:
                if behavior.target_type == "product" and behavior.target_id:
                    try:
                        product_id = int(behavior.target_id)
                        if product_id not in seen:
                            purchased_ids.append(product_id)
                            seen.add(product_id)
                    except (ValueError, TypeError):
                        logger.warning(f"无效的商品ID: {behavior.target_id}")
                        continue

            logger.info(f"提取用户已购买商品: user_id={user_id}, purchased_count={len(purchased_ids)}")
            return purchased_ids

        except Exception as e:
            logger.error(f"获取已购买商品异常: user_id={user_id}, error={str(e)}", exc_info=True)
            return []

    async def get_search_keywords(self, user_id: int, day: int = 30) -> List[str]:
        """
        获取用户最近的搜索关键词.

        Args:
            user_id: 用户ID
            day: 最近多少天

        Returns:
            搜索关键词列表（去重后，按时间倒序）
        """
        try:
            behaviors = await self.get_user_behaviors(
                user_id=user_id,
                day=day,
                behavior_type="search"
            )

            # 提取搜索关键词并去重（保持顺序）
            keywords = []
            seen = set()
            for behavior in behaviors:
                if behavior.search_keyword and behavior.search_keyword.strip():
                    keyword = behavior.search_keyword.strip()
                    if keyword not in seen:
                        keywords.append(keyword)
                        seen.add(keyword)

            logger.info(f"提取用户搜索关键词: user_id={user_id}, keyword_count={len(keywords)}",)
            return keywords

        except Exception as e:
            logger.error(
                f"获取搜索关键词异常: user_id={user_id}, error={str(e)}",
                exc_info=True
            )
            return []


# 单例实例
_user_service_client: Optional[UserServiceClient] = None


def get_user_service_client() -> UserServiceClient:
    """获取用户服务客户端单例."""
    global _user_service_client
    if _user_service_client is None:
        _user_service_client = UserServiceClient()
    return _user_service_client

