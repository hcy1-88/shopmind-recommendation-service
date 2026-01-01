"""
@File       : recommendation_router.py
@Description: Recommendation API endpoints

@Time       : 2026/01/01
@Author     : hcy18
"""
from typing import List
from fastapi import APIRouter, Query, HTTPException

from app.schemas.recommendation_schema import RecommendationResponse
from app.schemas.page_result_schema import PageResult
from app.schemas.product_service_schema import ProductResponseDto
from app.schemas.result_context import ResultContext
from app.services.recommendation_service import get_recommendation_service
from app.utils.logger import app_logger as logger
from app.utils.trace_context import get_trace_id

router = APIRouter(
    prefix="/recommend",
    tags=["Recommendation"],
)


@router.get("", response_model=ResultContext[RecommendationResponse])
async def recommend_products(
    user_id: int = Query(..., description="用户ID", alias="userId"),
    limit: int = Query(10, ge=1, le=100, description="推荐数量（1-100）")
) -> ResultContext[RecommendationResponse]:
    """
    为用户生成个性化商品推荐.

    **推荐逻辑**：
    1. 如果用户有 ≥3 条商品行为 → 基于行为的个性化推荐（向量检索）
    2. 否则 → 返回热门商品（冷启动）
    3. 任何环节失败 → 自动降级到热门商品

    **返回策略说明**：
    - `personalized`: 基于用户行为的个性化推荐
    - `cold_start`: 冷启动（无足够行为数据，返回热门商品）
    - `fallback`: 降级（推荐服务异常，返回热门商品兜底）
    """
    try:
        logger.info(f"收到推荐请求: user_id={user_id}, limit={limit}")

        # 调用推荐服务
        recommendation_service = get_recommendation_service()
        products, strategy = await recommendation_service.recommend(user_id=user_id, limit=limit)

        # 构建响应
        response = RecommendationResponse(
            products=products,
            strategy=strategy,
            total=len(products)
        )

        logger.info(
            f"推荐完成: user_id={user_id}, strategy={strategy}, count={len(products)}"
        )

        return ResultContext.ok(
            data=response,
            message="推荐成功"
        )

    except Exception as e:
        logger.error(f"推荐接口异常: user_id={user_id}, error={str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"推荐服务异常: {str(e)}"
        )



@router.get("/products/search", response_model=ResultContext[PageResult])
async def search_products(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    page_number: int = Query(1, ge=1, alias="pageNumber", description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize", description="每页大小，1-100")
) -> ResultContext[PageResult]:
    """
    商品语义搜索接口（支持分页）.

    **功能说明**：
    - 使用语义向量搜索，理解用户搜索意图
    - 支持分页，提高查询效率
    - 返回相似度最高的商品

    **搜索原理**：
    1. 将搜索关键词转换为向量（embedding）
    2. 在 Milvus 向量数据库中进行相似度搜索
    3. 返回最相关的商品（按相似度排序）

    **示例**：
    - 搜索 "女士夏季连衣裙" → 返回相关服饰
    - 搜索 "iPhone 手机" → 返回数码产品
    - 搜索 "运动鞋" → 返回运动装备
    """
    try:
        logger.info(f"收到搜索请求: keyword={keyword}, page={page_number}, size={page_size}")

        # 调用推荐服务的搜索功能
        recommendation_service = get_recommendation_service()
        page_result = await recommendation_service.search_products(
            keyword=keyword,
            page_number=page_number,
            page_size=page_size
        )

        logger.info(
            f"搜索完成: keyword={keyword}, page={page_number}, count={len(page_result.data)}, total={page_result.total}")

        return ResultContext.ok(
            data=page_result,
            message="搜索成功"
        )

    except Exception as e:
        logger.error(
            f"搜索接口异常: keyword={keyword}, error={str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"搜索服务异常: {str(e)}"
        )

