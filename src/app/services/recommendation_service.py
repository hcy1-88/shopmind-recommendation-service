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
from app.clients.redis_client import get_redis_client
from app.schemas.product_service_schema import ProductResponseDto
from app.schemas.page_result_schema import PageResult
from app.services.embedding_service import get_embedding_service
from app.store.product_collection import get_collection
from app.utils.logger import app_logger as logger
from app.config.nacos_client import get_nacos_client


class RecommendationService:
    """推荐服务核心类."""

    _instance: Optional["RecommendationService"] = None

    def __init__(self):
        self.user_client = get_user_service_client()
        self.product_client = get_product_service_client()
        self.redis_client = get_redis_client()
        self.embedding_service = get_embedding_service()
        self.nacos_client = get_nacos_client()
        self.min_behavior_count = 3  # 使用行为推荐的最少行为数, 默认 3
        self.user_behavior_history = 30  # 考虑的用户行为历史天数，默认 30 天的行为历史
        self.min_distance = 0.45  # 相似度阈值，低于则不被推荐
        self.vector_cache_ttl = 600  # 用户向量缓存时间（秒），默认 10 分钟


    def _initialize(self):
        self.config = self.nacos_client.get_recommendation_config()
        self.min_behavior_count = self.config["min_behavior_count"]
        self.user_behavior_history = self.config["user_behavior_history"]
        self.min_distance = self.config["min_distance"]
        self.vector_cache_ttl = self.config["vector_cache_ttl"]


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
        logger.info(f"开始生成推荐: user_id={user_id}, limit={limit}")

        try:
            # Step 1: 尝试从 Redis 获取用户向量
            cached_vector = await self.redis_client.get_user_vector(user_id)

            if cached_vector is not None:
                # 使用缓存的用户向量进行推荐
                logger.info(f"使用缓存的用户向量: user_id={user_id}")
                user_vector = np.array(cached_vector)

                # 获取已购买商品列表（用于过滤）
                purchased_product_ids = await self.user_client.get_purchased_products(user_id)

                # 向量搜索
                candidate_product_ids = await self._vector_search(
                    user_vector=user_vector,
                    top_k=limit * 3,
                )

                # 过滤已购买商品
                if purchased_product_ids:
                    purchased_set = set(purchased_product_ids)
                    filtered_ids = [pid for pid in candidate_product_ids if pid not in purchased_set][:limit]
                else:
                    filtered_ids = candidate_product_ids[:limit]

                # 获取商品详情
                if filtered_ids:
                    products = await self.product_client.get_products_by_ids(filtered_ids)
                    id_to_product = {p.id_int: p for p in products}
                    sorted_products = [id_to_product[pid] for pid in filtered_ids if pid in id_to_product]

                    if sorted_products:
                        logger.info(f"缓存向量推荐成功: user_id={user_id}, count={len(sorted_products)}")
                        return sorted_products, "personalized"

            # Step 2: 缓存未命中或推荐失败，执行完整推荐流程
            logger.info(f"执行完整推荐流程: user_id={user_id}")

            # 并行获取用户兴趣、行为历史和搜索关键词
            interests_task = self.user_client.get_user_interests(user_id)
            behaviors_task = self.user_client.get_product_behaviors(user_id, day=self.user_behavior_history)

            interests, interacted_product_ids = await asyncio.gather(
                interests_task, behaviors_task
            )

            has_interests = interests and interests.interests
            has_enough_behaviors = len(interacted_product_ids) >= self.min_behavior_count

            logger.info(
                f"用户数据获取完成: user_id={user_id}, "
                f"interests_count={len(interests.interests) if has_interests else 0}, "
                f"behavior_count={len(interacted_product_ids)}, ",
                extra={
                    "user_id": user_id,
                    "has_interests": has_interests,
                    "has_behaviors": has_enough_behaviors,
                }
            )

            # Step 3: 判断推荐策略 - 有兴趣、足够行为或搜索关键词则进行个性化推荐
            if has_interests or has_enough_behaviors:
                # 个性化推荐
                products = await self._personalized_recommend_with_cache(
                    user_id=user_id,
                    interests=interests.interests if has_interests else None,
                    interacted_product_ids=interacted_product_ids if has_enough_behaviors else None,
                    limit=limit
                )
                if products:
                    logger.info(f"个性化推荐成功: user_id={user_id}, count={len(products)}")
                    return products, "personalized"

            # Step 4: 冷启动或个性化失败 → 热门商品兜底
            logger.info(f"触发冷启动逻辑: user_id={user_id}, reason=无兴趣且行为数不足")
            products = await self.product_client.get_hot_products(limit=limit)

            if products:
                logger.info(f"返回热门商品: user_id={user_id}, count={len(products)}")
                return products, "cold_start"
            else:
                logger.warning(f"热门商品获取失败: user_id={user_id}")
                return [], "fallback"

        except Exception as e:
            logger.error(f"推荐生成异常: user_id={user_id}, error={str(e)}", exc_info=True)
            # 降级到热门商品
            try:
                products = await self.product_client.get_hot_products(limit=limit)
                return products, "fallback"
            except Exception:
                return [], "fallback"

    async def _personalized_recommend_with_cache(
        self,
        user_id: int,
        interests: Optional[Dict[str, str]] = None,
        interacted_product_ids: Optional[List[int]] = None,
        limit: int = 10
    ) -> List[ProductResponseDto]:
        """
        个性化推荐（支持基于兴趣、行为或搜索关键词），并缓存用户向量.

        Args:
            user_id: 用户ID
            interests: 用户兴趣标签 (key: 英文code, value: 中文名称)
            interacted_product_ids: 用户已交互的商品ID列表（用于生成基于行为的用户向量）
            limit: 推荐数量

        Returns:
            推荐商品列表
            
        Note:
            - 只会过滤已购买（purchase）的商品
            - 其他行为（view/like/share/add_cart）的商品仍会被推荐
        """
        try:
            # 生成用户向量
            user_vector = await self._compute_user_vector(
                user_id=user_id,
                interests=interests,
                interacted_product_ids=interacted_product_ids,
            )

            if user_vector is None:
                logger.warning(f"无法生成用户向量: user_id={user_id}")
                return []

            # 缓存用户向量到 Redis
            await self.redis_client.set_user_vector(
                user_id=user_id,
                vector=user_vector.tolist(),
                ttl=self.vector_cache_ttl
            )

            # 向量搜索
            candidate_product_ids = await self._vector_search(
                user_vector=user_vector,
                top_k=limit * 3,
            )

            if not candidate_product_ids:
                logger.warning(f"向量搜索无结果: user_id={user_id}")
                return []

            # 获取已购买商品（用于过滤）
            purchased_product_ids = await self.user_client.get_purchased_products(user_id)

            # 过滤已购买商品
            if purchased_product_ids:
                purchased_set = set(purchased_product_ids)
                filtered_ids = [pid for pid in candidate_product_ids if pid not in purchased_set][:limit]
                logger.info(f"过滤已购买商品: user_id={user_id}, purchased_count={len(purchased_product_ids)}, filtered_out={len([pid for pid in candidate_product_ids if pid in purchased_set])}")
            else:
                filtered_ids = candidate_product_ids[:limit]

            if not filtered_ids:
                logger.warning(f"过滤后无推荐商品: user_id={user_id}")
                return []

            # 获取商品详情
            products = await self.product_client.get_products_by_ids(filtered_ids)
            id_to_product = {p.id_int: p for p in products}
            sorted_products = [id_to_product[pid] for pid in filtered_ids if pid in id_to_product]

            logger.info(f"个性化推荐完成: user_id={user_id}, count={len(sorted_products)}")
            return sorted_products

        except Exception as e:
            logger.error(f"个性化推荐异常: user_id={user_id}, error={str(e)}", exc_info=True)
            return []

    async def _compute_user_vector(
        self,
        user_id: int,
        interests: Optional[Dict[str, str]] = None,
        interacted_product_ids: Optional[List[int]] = None,
    ) -> Optional[np.ndarray]:
        """
        计算用户向量（融合行为、兴趣、搜索关键词）.

        Args:
            user_id: 用户ID
            interests: 用户兴趣标签
            interacted_product_ids: 用户已交互的商品ID列表（用于生成基于行为的向量）

        Returns:
            用户向量（numpy array），如果失败返回 None
            
        Note:
            interacted_product_ids 包含所有交互行为（view/like/share/add_cart等），
            用于更全面地理解用户兴趣
        """
        try:
            user_vectors = []
            strategies_used = []

            # 1. 基于行为生成向量
            if interacted_product_ids and len(interacted_product_ids) >= self.min_behavior_count:
                behavior_vector = await self._get_user_vector_from_behaviors(interacted_product_ids)
                if behavior_vector is not None:
                    user_vectors.append(behavior_vector)
                    strategies_used.append("behavior")
                    logger.info(f"使用行为生成用户向量: user_id={user_id}, behavior_count={len(interacted_product_ids)}")

            # 2. 基于兴趣生成向量
            if interests:
                interest_vector = await self._get_user_vector_from_interests(interests)
                if interest_vector is not None:
                    user_vectors.append(interest_vector)
                    strategies_used.append("interest")
                    logger.info(f"使用兴趣生成用户向量: user_id={user_id}, interest_count={len(interests)}")

            # 3. 融合多个向量
            if not user_vectors:
                logger.warning(f"无法生成用户向量: user_id={user_id}")
                return None

            if len(user_vectors) > 1:
                user_vector = np.mean(user_vectors, axis=0)
                strategy_used = "+".join(strategies_used)
                logger.info(f"融合多个向量: user_id={user_id}, strategies={strategy_used}")
            else:
                user_vector = user_vectors[0]

            return user_vector

        except Exception as e:
            logger.error(f"计算用户向量异常: user_id={user_id}, error={str(e)}", exc_info=True)
            return None

    async def _personalized_recommend(
        self,
        user_id: int,
        interests: Optional[Dict[str, str]] = None,
        interacted_product_ids: Optional[List[int]] = None,
        limit: int = 10
    ) -> List[ProductResponseDto]:
        """
        个性化推荐（支持基于兴趣、行为或搜索关键词）.

        Args:
            user_id: 用户ID
            interests: 用户兴趣标签 (key: 英文code, value: 中文名称)
            interacted_product_ids: 用户已交互的商品ID列表（用于生成基于行为的用户向量）
            limit: 推荐数量

        Returns:
            推荐商品列表
            
        Note:
            - 只会过滤已购买（purchase）的商品
            - 其他行为（view/like/share/add_cart）的商品仍会被推荐
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


            # 1.3 融合多个向量（如果有多个来源）
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

            # Step 3: 过滤已购买商品
            purchased_product_ids = await self.user_client.get_purchased_products(user_id)
            if purchased_product_ids:
                purchased_set = set(purchased_product_ids)
                filtered_ids = [pid for pid in candidate_product_ids if pid not in purchased_set][:limit]
                logger.info(f"过滤已购买商品: user_id={user_id}, purchased_count={len(purchased_product_ids)}")
            else:
                filtered_ids = candidate_product_ids[:limit]

            if not filtered_ids:
                logger.warning(
                    f"过滤后无推荐商品: user_id={user_id}")
                return []

            # Step 4: 批量获取商品详情
            products = await self.product_client.get_products_by_ids(filtered_ids)

            # Step 5: 按搜索顺序排序（保持相似度顺序）
            id_to_product = {p.id_int: p for p in products}
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

            # 提取向量并去重（同一个 product_id 只保留一个）
            product_embeddings = {}
            for item in results:
                pid = item["product_id"]
                if pid not in product_embeddings:
                    product_embeddings[pid] = np.array(item["embedding"])

            # 进行平均池化
            embeddings = list(product_embeddings.values())
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

    async def _get_user_vector_from_keywords(self, keywords: list[str]) -> Optional[np.ndarray]:
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
                "metric_type": "COSINE",
                "params": {"ef": 64}
            }

            # 执行搜索
            results = collection.search(
                data=[user_vector.tolist()],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["product_id"]
            )

            # 提取商品ID（去重，保持顺序）
            product_ids = []
            seen = set()
            if results and len(results) > 0:
                for hit in results[0]:
                    product_id = hit.entity.get("product_id")
                    if product_id:
                        pid = int(product_id)
                        if pid not in seen:
                            product_ids.append(pid)
                            seen.add(pid)

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
                "metric_type": "COSINE",
                "params": {"ef": 64}
            }
            # SearchResult
            results = collection.search(
                data=[np.array(search_vector).tolist()],
                anns_field="embedding",
                param=search_params,
                limit=search_limit,
                output_fields=["product_id"]  # 只取商品 id
            )

            # Step 4: 提取商品ID（去重，保持顺序）
            all_product_ids = []
            seen = set()
            if results and len(results) > 0:
                for hit in results[0]:  # results[0] 的类型是 HybridHits
                    product_id = hit.entity.get("product_id")     # 每一个 hit 是 Hit 对象，格式 {'id':'1', 'distance': 0.2, 'entity':搜索记录}
                    if product_id and hit.distance >= self.min_distance:
                        pid = int(product_id)
                        if pid not in seen:
                            all_product_ids.append(pid)
                            seen.add(pid)
                            logger.info(f"搜索商品: product_id={product_id}， distance={hit.distance}")

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
            id_to_product = {p.id_int: p for p in products}
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

    async def get_similar_products(self, product_id: int, limit: int = 10) -> List[ProductResponseDto]:
        """
        根据商品ID获取相似商品推荐.

        Args:
            product_id: 商品ID
            limit: 推荐数量

        Returns:
            相似商品列表
        """
        try:
            logger.info(f"开始获取相似商品: product_id={product_id}, limit={limit}")

            # Step 1: 从 Milvus 获取该商品的向量
            collection = get_collection()
            collection.load()

            query_expr = f"product_id == {product_id}"
            results = collection.query(
                expr=query_expr,
                output_fields=["product_id", "embedding"]
            )

            if not results or len(results) == 0:
                logger.warning(f"商品向量不存在: product_id={product_id}")
                return []

            # 获取商品向量（如果有多条取第一条）
            product_vector = np.array(results[0]["embedding"])
            logger.info(f"获取商品向量成功: product_id={product_id}, dim={len(product_vector)}")

            # Step 2: 使用商品向量进行相似度搜索
            search_params = {
                "metric_type": "COSINE",
                "params": {"ef": 64}
            }

            search_results = collection.search(
                data=[product_vector.tolist()],
                anns_field="embedding",
                param=search_params,
                limit=limit + 10,  # 多取一些，过滤后保证足够数量
                output_fields=["product_id"]
            )

            # Step 3: 提取相似商品ID（去重并过滤掉商品自己）
            similar_product_ids = []
            seen = set()
            seen.add(product_id)  # 先把自己加入，避免推荐自己

            if search_results and len(search_results) > 0:
                for hit in search_results[0]:
                    pid = hit.entity.get("product_id")
                    if pid and pid not in seen and hit.distance >= self.min_distance:
                        similar_product_ids.append(int(pid))
                        seen.add(int(pid))
                        if len(similar_product_ids) >= limit:
                            break

            if not similar_product_ids:
                logger.warning(f"未找到相似商品: product_id={product_id}")
                return []

            logger.info(f"找到相似商品: product_id={product_id}, count={len(similar_product_ids)}")

            # Step 4: 批量获取商品详情
            products = await self.product_client.get_products_by_ids(similar_product_ids)

            # Step 5: 按相似度顺序排序
            id_to_product = {p.id_int: p for p in products}
            sorted_products = [id_to_product[pid] for pid in similar_product_ids if pid in id_to_product]

            logger.info(f"相似商品推荐完成: product_id={product_id}, returned={len(sorted_products)}")
            return sorted_products

        except Exception as e:
            logger.error(f"获取相似商品异常: product_id={product_id}, error={str(e)}", exc_info=True)
            return []

    async def refresh_user_vectors_task(self):
        """
        定时刷新用户向量任务（后台运行）.
        """
        logger.info("用户向量定时刷新任务启动")

        while True:
            try:
                # 等待刷新间隔（默认 10 分钟）
                await asyncio.sleep(self.vector_cache_ttl)

                logger.info("开始刷新用户向量...")

                # TODO: 这里可以从用户服务获取活跃用户列表
                # 目前简单实现：只刷新 Redis 中已有的用户向量
                # 实际生产中，可以维护一个活跃用户列表

                logger.info("用户向量刷新完成")

            except asyncio.CancelledError:
                logger.info("用户向量刷新任务已取消")
                break
            except Exception as e:
                logger.error(f"刷新用户向量异常: {e}", exc_info=True)
                # 继续运行，不中断定时任务

    async def refresh_user_vector(self, user_id: int):
        """
        刷新单个用户的向量.

        Args:
            user_id: 用户ID
        """
        try:
            logger.info(f"开始刷新用户向量: user_id={user_id}")

            # 获取用户数据
            interests_task = self.user_client.get_user_interests(user_id)
            behaviors_task = self.user_client.get_product_behaviors(user_id, day=self.user_behavior_history)

            interests, interacted_product_ids = await asyncio.gather(
                interests_task, behaviors_task, return_exceptions=True
            )

            # 检查是否有异常
            if isinstance(interests, Exception):
                logger.error(f"获取用户兴趣失败: user_id={user_id}, error={interests}")
                return
            if isinstance(interacted_product_ids, Exception):
                logger.error(f"获取用户行为失败: user_id={user_id}, error={interacted_product_ids}")
                return


            has_interests = interests and interests.interests
            has_enough_behaviors = len(interacted_product_ids) >= self.min_behavior_count

            # 只有当用户有数据时才更新向量
            if not (has_interests or has_enough_behaviors):
                logger.info(f"用户无有效数据，跳过刷新: user_id={user_id}")
                return

            # 计算用户向量
            user_vector = await self._compute_user_vector(
                user_id=user_id,
                interests=interests.interests if has_interests else None,
                interacted_product_ids=interacted_product_ids if has_enough_behaviors else None,
            )

            if user_vector is not None:
                # 更新 Redis 缓存
                await self.redis_client.set_user_vector(
                    user_id=user_id,
                    vector=user_vector.tolist(),
                    ttl=self.vector_cache_ttl
                )
                logger.info(f"用户向量刷新成功: user_id={user_id}")
            else:
                logger.warning(f"无法生成用户向量: user_id={user_id}")

        except Exception as e:
            logger.error(f"刷新用户向量异常: user_id={user_id}, error={e}", exc_info=True)

    @classmethod
    def get_instance(cls) -> "RecommendationService":
        """统一单例"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._initialize()
        return cls._instance


def get_recommendation_service() -> RecommendationService:
    """获取推荐服务单例."""
    return RecommendationService.get_instance()

