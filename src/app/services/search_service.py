"""
@File       : search_service.py
@Description:

@Time       : 2026/1/4 19:13
@Author     : hcy18
"""
from app.services.embedding_service import get_embedding_service
from app.store.product_collection import get_collection
from app.utils.logger import app_logger as logger


class SearchService:
    @staticmethod
    async def rerank_product_id_by_semantics(keyword: str, limit: int, product_ids: list[int] = None) -> list[int]:
        """搜索商品"""
        # Step 1: 使用 embedding 服务将关键词转为向量
        search_vector = await get_embedding_service().embed_query(keyword)

        if not search_vector:
            logger.warning(
                f"关键词向量生成失败: keyword={keyword}")
            return list()

        # Step 2: 搜索
        logger.info(f"关键词向量生成成功: keyword={keyword}, vector_dim={len(search_vector)}")

        collection = get_collection()
        collection.load()

        search_params = {
            "metric_type": "COSINE",
            "params": {"ef": 64}
        }
        # Step 3: 语义精排，对 product ids 进行排序，返回 limit
        logger.info(f"请求参数中的 product_ids 个数: {len(product_ids)}")
        expr = ""
        if product_ids:
            if len(product_ids) == 1:
                expr = f"product_id == {product_ids[0]}"
            else:
                expr = f"product_id in [{','.join(map(str, product_ids))}]"

        results = collection.search(
            data=[search_vector],
            anns_field="embedding",
            param=search_params,
            expr=expr,
            limit=min(limit, len(product_ids)) if product_ids else limit,
            output_fields=["product_id"]  # 只取商品 id
        )

        # Step 4: 解析结果
        seen = set()
        ranked_ids = []
        if results and len(results[0]) > 0:
            for hit in results[0]:
                pid = hit.entity.get("product_id")
                if pid is not None and pid not in seen:
                    seen.add(pid)
                    ranked_ids.append(pid)

        logger.info(f"语义搜索并排序成功，关键词：{keyword}, 语义召回个数：{len(ranked_ids)}")
        return ranked_ids
