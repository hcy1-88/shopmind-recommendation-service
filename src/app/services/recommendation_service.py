"""
@File       : recommendation_service.py
@Description: Core recommendation service with vector search and cold start logic

@Time       : 2026/01/01
@Author     : hcy18
"""
from typing import List, Tuple, Optional, Dict
import numpy as np
import asyncio
from app.clients.user_service_client import get_user_service_client
from app.clients.product_service_client import get_product_service_client
from app.schemas.product_service_schema import ProductResponseDto
from app.schemas.page_result_schema import PageResult
from app.services.embedding_service import get_embedding_service
from app.store.product_collection import get_collection
from app.utils.logger import app_logger as logger


class RecommendationService:
    """推荐服务核心类."""

    def __init__(self):
        self.user_client = get_user_service_client()
        self.product_client = get_product_service_client()
        self.embedding_service = get_embedding_service()
        self.min_behavior_count = 3  # 使用行为推荐的最少行为数

    async def recommend(self, user_id: int, limit: int = 10) -> Tuple[List[ProductResponseDto], str]:
        """
        为用户生成个性化推荐.

        Args:
            user_id: 用户ID
            limit: 推荐数量

        Returns:
            (推荐商品列表, 推荐策略)
            推荐策略: 'personalized' | 'cold_start' | 'fallback'
        """
        logger.info(
            f"开始生成推荐: user_id={user_id}, limit={limit}")

        try:
            # Step 1: 并行获取用户兴趣、行为历史和搜索关键词
            interests_task = self.user_client.get_user_interests(user_id)
            behaviors_task = self.user_client.get_product_behaviors(user_id, day=7)
            keywords_task = self.user_client.get_search_keywords(user_id, day=7)

            # 等待并发结果
            interests, interacted_product_ids, search_keywords = await asyncio.gather(
                interests_task, behaviors_task, keywords_task
            )

            has_interests = interests and interests.interests
            has_enough_behaviors = len(interacted_product_ids) >= self.min_behavior_count
            has_search_keywords = len(search_keywords) > 0

            logger.info(
                f"用户数据获取完成: user_id={user_id}, "
                f"interests_count={len(interests.interests) if has_interests else 0}, "
                f"behavior_count={len(interacted_product_ids)}, "
                f"search_keyword_count={len(search_keywords)}",
                extra={
                    "user_id": user_id,
                    "has_interests": has_interests,
                    "has_behaviors": has_enough_behaviors,
                    "has_keywords": has_search_keywords
                }
            )

            # Step 2: 判断推荐策略 - 有兴趣、足够行为或搜索关键词则进行个性化推荐
            if has_interests or has_enough_behaviors or has_search_keywords:
                # 个性化推荐
                products = await self._personalized_recommend(
                    user_id=user_id,
                    interests=interests.interests if has_interests else None,
                    interacted_product_ids=interacted_product_ids if has_enough_behaviors else None,
                    search_keywords=search_keywords if has_search_keywords else None,
                    limit=limit
                )
                if products:
                    logger.info(
                        f"个性化推荐成功: user_id={user_id}, count={len(products)}")
                    return products, "personalized"

            # Step 3: 冷启动或个性化失败 → 热门商品兜底
            logger.info(
                f"触发冷启动逻辑: user_id={user_id}, reason=无兴趣且行为数不足")
            products = await self.product_client.get_hot_products(limit=limit)

            if products:
                logger.info(f"返回热门商品: user_id={user_id}, count={len(products)}")
                return products, "cold_start"
            else:
                logger.warning(
                    f"热门商品获取失败: user_id={user_id}")
                return [], "fallback"

        except Exception as e:
            logger.error(
                f"推荐生成异常: user_id={user_id}, error={str(e)}",
                exc_info=True
            )
            # 降级到热门商品
            try:
                products = await self.product_client.get_hot_products(limit=limit)
                return products, "fallback"
            except Exception:
                return [], "fallback"

    async def _personalized_recommend(
        self,
        user_id: int,
        interests: Optional[Dict[str, str]] = None,
        interacted_product_ids: Optional[List[int]] = None,
        search_keywords: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[ProductResponseDto]:
        """
        个性化推荐（支持基于兴趣、行为或搜索关键词）.

        Args:
            user_id: 用户ID
            interests: 用户兴趣标签 (key: 英文code, value: 中文名称)
            interacted_product_ids: 用户已交互的商品ID列表
            search_keywords: 用户搜索关键词列表
            limit: 推荐数量

        Returns:
            推荐商品列表
        """
        try:
            user_vectors = []
            strategies_used = []

            # Step 1: 生成用户向量（可能融合多个来源）
            # 1.1 基于行为生成向量
            if interacted_product_ids and len(interacted_product_ids) >= self.min_behavior_count:
                behavior_vector = await self._get_user_vector_from_behaviors(interacted_product_ids)
                if behavior_vector is not None:
                    user_vectors.append(behavior_vector)
                    strategies_used.append("behavior")
                    logger.info(
                        f"使用行为生成用户向量: user_id={user_id}, behavior_count={len(interacted_product_ids)}")
            
            # 1.2 基于兴趣生成向量
            if interests:
                interest_vector = await self._get_user_vector_from_interests(interests)
                if interest_vector is not None:
                    user_vectors.append(interest_vector)
                    strategies_used.append("interest")
                    logger.info(
                        f"使用兴趣生成用户向量: user_id={user_id}, interest_count={len(interests)}")

            # 1.3 基于搜索关键词生成向量
            if search_keywords:
                keyword_vector = await self._get_user_vector_from_keywords(search_keywords)
                if keyword_vector is not None:
                    user_vectors.append(keyword_vector)
                    strategies_used.append("search")
                    logger.info(
                        f"使用搜索关键词生成用户向量: user_id={user_id}, keyword_count={len(search_keywords)}, keywords={search_keywords[:5]}")

            # 1.4 融合多个向量（如果有多个来源）
            if not user_vectors:
                logger.warning(
                    f"无法生成用户向量: user_id={user_id}")
                return []

            if len(user_vectors) > 1:
                # 多个向量取平均
                user_vector = np.mean(user_vectors, axis=0)
                strategy_used = "+".join(strategies_used)
                logger.info(
                    f"融合多个向量: user_id={user_id}, strategies={strategy_used}")
            else:
                user_vector = user_vectors[0]
                strategy_used = strategies_used[0]

            if user_vector is None:
                logger.warning(
                    f"无法生成用户向量: user_id={user_id}")
                return []

            # Step 2: 在 Milvus 中进行向量搜索
            candidate_product_ids = await self._vector_search(
                user_vector=user_vector,
                top_k=limit * 3,  # 多取一些，用于过滤后仍有足够数量
            )

            if not candidate_product_ids:
                logger.warning(
                    f"向量搜索无结果: user_id={user_id}")
                return []

            # Step 3: 过滤已交互商品
            if interacted_product_ids:
                interacted_set = set(interacted_product_ids)
                filtered_ids = [pid for pid in candidate_product_ids if pid not in interacted_set][:limit]
            else:
                filtered_ids = candidate_product_ids[:limit]

            if not filtered_ids:
                logger.warning(
                    f"过滤后无推荐商品: user_id={user_id}")
                return []

            # Step 4: 批量获取商品详情
            products = await self.product_client.get_products_by_ids(filtered_ids)

            # Step 5: 按搜索顺序排序（保持相似度顺序）
            id_to_product = {p.id: p for p in products}
            sorted_products = [id_to_product[pid] for pid in filtered_ids if pid in id_to_product]

            logger.info(
                f"个性化推荐完成: user_id={user_id}, strategy={strategy_used}, count={len(sorted_products)}")
            return sorted_products

        except Exception as e:
            logger.error(
                f"个性化推荐异常: user_id={user_id}, error={str(e)}",
                exc_info=True
            )
            return []

    async def _get_user_vector_from_behaviors(self, product_ids: List[int]) -> Optional[np.ndarray]:
        """
        根据用户交互的商品ID，生成用户向量（平均池化）.

        Args:
            product_ids: 商品ID列表

        Returns:
            用户向量（numpy array），如果失败返回 None
        """
        try:
            collection = get_collection()
            collection.load()

            # 从 Milvus 查询商品向量
            query_expr = f"product_id in {product_ids}"
            results = collection.query(
                expr=query_expr,
                output_fields=["product_id", "embedding"]
            )

            if not results:
                logger.warning(
                    f"未找到任何商品向量: product_ids={product_ids}")
                return None

            # 提取向量并进行平均池化
            embeddings = [np.array(item["embedding"]) for item in results]
            user_vector = np.mean(embeddings, axis=0)

            logger.info(
                f"基于行为生成用户向量: product_count={len(embeddings)}, vector_dim={len(user_vector)}")
            return user_vector

        except Exception as e:
            logger.error(
                f"基于行为生成用户向量异常: error={str(e)}",
                exc_info=True
            )
            return None

    async def _get_user_vector_from_interests(self, interests: Dict[str, str]) -> Optional[np.ndarray]:
        """
        根据用户兴趣标签生成用户向量.

        Args:
            interests: 用户兴趣标签 (key: 英文code, value: 中文名称)

        Returns:
            用户向量（numpy array），如果失败返回 None
        """
        try:
            if not interests:
                return None

            # 将兴趣标签组合成查询文本
            # 使用中文名称，因为更有语义信息
            interest_texts = list(interests.values())
            query_text = " ".join(interest_texts)

            logger.info(f"基于兴趣生成向量: query_text={query_text}")

            # 使用 embedding 服务生成向量
            user_vector = await self.embedding_service.embed_query(query_text)

            if not user_vector:
                logger.warning(f"兴趣向量生成失败")
                return None

            # 转换为 numpy array
            user_vector = np.array(user_vector)

            logger.info(
                f"基于兴趣生成用户向量成功: interest_count={len(interests)}, vector_dim={len(user_vector)}")
            return user_vector

        except Exception as e:
            logger.error(
                f"基于兴趣生成用户向量异常: error={str(e)}",
                exc_info=True
            )
            return None

    async def _get_user_vector_from_keywords(self, keywords: List[str]) -> Optional[np.ndarray]:
        """
        根据用户搜索关键词生成用户向量.

        Args:
            keywords: 用户搜索关键词列表

        Returns:
            用户向量（numpy array），如果失败返回 None
        """
        try:
            if not keywords:
                return None

            # 将搜索关键词组合成查询文本
            # 取前5个最近的搜索关键词
            recent_keywords = keywords[:5]
            query_text = " ".join(recent_keywords)

            logger.info(f"基于搜索关键词生成向量: query_text={query_text}")

            # 使用 embedding 服务生成向量
            user_vector = await self.embedding_service.embed_query(query_text)

            if not user_vector:
                logger.warning(f"搜索关键词向量生成失败")
                return None

            # 转换为 numpy array
            user_vector = np.array(user_vector)

            logger.info(
                f"基于搜索关键词生成用户向量成功: keyword_count={len(recent_keywords)}, vector_dim={len(user_vector)}")
            return user_vector

        except Exception as e:
            logger.error(
                f"基于搜索关键词生成用户向量异常: error={str(e)}",
                exc_info=True
            )
            return None

    async def _vector_search(
        self,
        user_vector: np.ndarray,
        top_k: int,
    ) -> List[int]:
        """
        在 Milvus 中进行向量搜索.

        Args:
            user_vector: 用户向量
            top_k: 返回前 K 个结果

        Returns:
            推荐的商品ID列表（按相似度排序）
        """
        try:
            collection = get_collection()
            collection.load()

            # 构建搜索参数
            search_params = {
                "metric_type": "IP",  # 内积相似度（假设向量已归一化）
                "params": {"nprobe": 10}
            }

            # 执行搜索
            results = collection.search(
                data=[user_vector.tolist()],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["product_id"]
            )

            # 提取商品ID
            product_ids = []
            if results and len(results) > 0:
                for hit in results[0]:
                    product_id = hit.entity.get("product_id")
                    if product_id:
                        product_ids.append(int(product_id))

            logger.info(
                f"向量搜索完成: found={len(product_ids)}, top_k={top_k}")
            return product_ids

        except Exception as e:
            logger.error(
                f"向量搜索异常: error={str(e)}",
                exc_info=True
            )
            return []

    async def search_products(
        self,
        keyword: str,
        page_number: int = 1,
        page_size: int = 10
    ) -> PageResult:
        """
        基于关键词的语义搜索（支持分页）.

        Args:
            keyword: 搜索关键词
            page_number: 页码（从1开始）
            page_size: 每页大小

        Returns:
            分页结果（包含商品列表、总数、页码、页大小）
        """
        logger.info(
            f"开始语义搜索: keyword={keyword}, page={page_number}, size={page_size}",)

        try:
            # Step 1: 使用 embedding 服务将关键词转为向量
            search_vector = await self.embedding_service.embed_query(keyword)
            
            if not search_vector:
                logger.warning(
                    f"关键词向量生成失败: keyword={keyword}")
                return PageResult(
                    data=[],
                    total=0,
                    page_number=page_number,
                    page_size=page_size
                )

            # Step 2: 计算需要搜索的数量（为了支持分页）
            # 搜索 (page_number * page_size) 个结果，然后取最后一页
            search_limit = page_number * page_size

            logger.info(f"关键词向量生成成功: keyword={keyword}, vector_dim={len(search_vector)}")

            # Step 3: 在 Milvus 中进行向量搜索
            collection = get_collection()
            collection.load()

            search_params = {
                "metric_type": "IP",  # 内积相似度
                "params": {"nprobe": 10}
            }

            results = collection.search(
                data=[np.array(search_vector).tolist()],
                anns_field="embedding",
                param=search_params,
                limit=search_limit,
                output_fields=["product_id"]
            )

            # Step 4: 提取商品ID
            all_product_ids = []
            if results and len(results) > 0:
                for hit in results[0]:
                    product_id = hit.entity.get("product_id")
                    if product_id:
                        all_product_ids.append(int(product_id))

            total = len(all_product_ids)

            logger.info(f"向量搜索完成: keyword={keyword}, total={total}")

            # Step 5: 分页处理
            start_index = (page_number - 1) * page_size
            end_index = start_index + page_size
            page_product_ids = all_product_ids[start_index:end_index]

            if not page_product_ids:
                logger.info(f"当前页无数据: page={page_number}")
                return PageResult(
                    data=[],
                    total=total,
                    page_number=page_number,
                    page_size=page_size
                )

            # Step 6: 批量获取商品详情
            products = await self.product_client.get_products_by_ids(page_product_ids)

            # Step 7: 按搜索顺序排序
            id_to_product = {p.id: p for p in products}
            sorted_products = [id_to_product[pid] for pid in page_product_ids if pid in id_to_product]

            logger.info(
                f"搜索完成: keyword={keyword}, page={page_number}, returned={len(sorted_products)}, total={total}")

            return PageResult(
                data=sorted_products,
                total=total,
                page_number=page_number,
                page_size=page_size
            )

        except Exception as e:
            logger.error(
                f"搜索异常: keyword={keyword}, error={str(e)}",
                exc_info=True
            )
            # 返回空结果
            return PageResult(
                data=[],
                total=0,
                page_number=page_number,
                page_size=page_size
            )


# 单例实例
_recommendation_service: Optional[RecommendationService] = None


def get_recommendation_service() -> RecommendationService:
    """获取推荐服务单例."""
    global _recommendation_service
    if _recommendation_service is None:
        _recommendation_service = RecommendationService()
    return _recommendation_service

