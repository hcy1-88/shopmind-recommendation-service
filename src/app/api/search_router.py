"""
@File       : search_router.py
@Description:

@Time       : 2026/1/3 20:52
@Author     : hcy18
"""
from app.schemas.result_context import ResultContext
from fastapi import APIRouter
from app.schemas.search_schema import ProductSemanticSearchRequest
from app.services.search_service import SearchService

router = APIRouter(prefix="/semantic", tags=["search semantic for coordinating"])


@router.post(
    "",
    response_model=ResultContext[list[int]],
    summary="纯语义搜索，返回商品 Id",
    description="根据关键词进行纯语义搜索，并排序，返回 limit 个，可选地对商品 id 过滤"
)
async def search_product_id_by_semantics(request: ProductSemanticSearchRequest) -> ResultContext[list[int]]:
    """调用 service 完成接口功能"""
    ids = await SearchService.search_product_id_by_semantics(request.keyword, request.limit, request.product_ids)
    return ResultContext.ok(ids)
