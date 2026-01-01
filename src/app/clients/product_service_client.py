"""
@File       : product_service_client.py
@Description: Client for calling product service APIs

@Time       : 2026/01/01
@Author     : hcy18
"""
from typing import List, Optional, Dict
import httpx

from app.clients.service_discovery import get_product_service_url
from app.schemas.product_service_schema import ProductResponseDto, ProductGettingRequestDTO
from app.schemas.result_context import ResultContext
from app.utils.logger import app_logger as logger
from app.utils.trace_context import get_trace_id, TRACE_ID_HEADER


class ProductServiceClient:
    """商品服务客户端."""

    def __init__(self):
        self._base_url: Optional[str] = None
        self.timeout = 10.0  # 请求超时时间（秒）

    async def _get_base_url(self) -> str:
        """获取商品服务的基础 URL（带缓存）."""
        if not self._base_url:
            self._base_url = await get_product_service_url()
        return self._base_url

    def _get_headers(self) -> Dict[str, str]:
        """获取带 Trace ID 的请求头."""
        trace_id = get_trace_id()
        return {
            TRACE_ID_HEADER: trace_id,
            "Content-Type": "application/json"
        }

    async def get_products_by_ids(self, product_ids: List[int]) -> List[ProductResponseDto]:
        """
        批量获取商品详情.

        Args:
            product_ids: 商品ID列表

        Returns:
            商品详情列表，如果失败返回空列表
        """
        if not product_ids:
            return []

        try:
            base_url = await self._get_base_url()
            url = f"{base_url}/products/ids"
            headers = self._get_headers()

            request_body = ProductGettingRequestDTO(ids=product_ids)

            logger.info(f"调用商品服务批量获取商品数量: count={len(product_ids)}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=request_body.model_dump(),
                    headers=headers
                )
                response.raise_for_status()
                
                products_result_context = ResultContext[list[ProductResponseDto]](**response.json())

                if products_result_context.success:
                    products = products_result_context.data
                    logger.info(
                        f"批量获取商品成功: requested={len(product_ids)}, returned={len(products)}",
                        extra={"requested": len(product_ids), "returned": len(products)}
                    )
                    return products
                else:
                    logger.error(f"请求商品商品失败！url: {url}, request:{request_body.model_dump()}")
                    raise httpx.HTTPError("商品服务异常！")
        except httpx.TimeoutException:
            logger.error(f"批量获取商品超时: product_ids={product_ids[:10]}")
            raise
        except Exception as e:
            logger.error(
                f"批量获取商品异常: error={str(e)}",
                exc_info=True
            )
            raise

    async def get_hot_products(self, limit: int = 10) -> List[ProductResponseDto]:
        """
        获取热门商品（冷启动兜底）.

        Args:
            limit: 限制数量

        Returns:
            热门商品列表，如果失败返回空列表
        """
        try:
            base_url = await self._get_base_url()
            url = f"{base_url}/products/hot"
            headers = self._get_headers()

            logger.info(f"调用商品服务获取热门商品: limit={limit}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params={"limit": limit}, headers=headers)
                response.raise_for_status()
                products_result_context = ResultContext[list[ProductResponseDto]](**response.json())
                if products_result_context.success:
                    products = products_result_context.data
                    logger.info(f"获取热门商品成功: count={len(products)}")
                    return products
                else:
                    logger.error(f"请求热门商品失败！url: {url}, limit:{limit}")
                    raise httpx.HTTPError("商品服务异常！")
        except httpx.TimeoutException:
            logger.error(f"获取热门商品超时: limit={limit}")
            raise
        except Exception as e:
            logger.error(f"获取热门商品异常: error={str(e)}",exc_info=True)
            raise


# 单例实例
_product_service_client: Optional[ProductServiceClient] = None


def get_product_service_client() -> ProductServiceClient:
    """获取商品服务客户端单例."""
    global _product_service_client
    if _product_service_client is None:
        _product_service_client = ProductServiceClient()
    return _product_service_client

