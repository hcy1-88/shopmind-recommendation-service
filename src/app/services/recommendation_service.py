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


BEHAVIOR_TYPE_SURPORTED = ["purchase", "add_cart", "like", "share", "view"]
# 行为权重配置（按重要性从高到低）
BEHAVIOR_WEIGHTS = {
    "purchase": 3.0,   # 购买行为 - 最强的转化信号
    "add_cart": 2.5,   # 加入购物车 - 强烈的购买意向
    "like": 2.0,       # 点赞 - 明确的正向反馈
    "share": 1.5,      # 分享 - 愿意推荐给他人
    "view": 1.0,       # 浏览 - 基础兴趣信号
    # 注意：search 行为没有 target_id，只有 search_keyword，会单独处理
}

# 向量融合权重配置
VECTOR_FUSION_WEIGHTS = {
    "behavior": 0.6,  # 行为向量权重（稍高）
    "interest": 0.4,  # 兴趣向量权重
}


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

            # 并行获取用户兴趣、分组行为历史和搜索关键词
            interests_task = self.user_client.get_user_interests(user_id)
            grouped_behaviors_task = self.user_client.get_user_behaviors_grouped(
                user_id, day=self.user_behavior_history
            )
            search_keywords_task = self.user_client.get_search_keywords(
                user_id, day=self.user_behavior_history
            )

            interests, grouped_behaviors, search_keywords = await asyncio.gather(
                interests_task, grouped_behaviors_task, search_keywords_task
            )

            # 计算有效行为数（所有有 target_id 的行为类型）
            behavior_count = sum(
                len(grouped_behaviors.get(bt, [])) 
                for bt in BEHAVIOR_TYPE_SURPORTED
            )
            
            has_interests = interests and interests.interests
            has_enough_behaviors = behavior_count >= self.min_behavior_count
            has_search_keywords = search_keywords and len(search_keywords) > 0

            logger.info(
                f"用户数据获取完成: user_id={user_id}, "
                f"interests_count={len(interests.interests) if has_interests else 0}, "
                f"behavior_count={behavior_count}, "
                f"search_keyword_count={len(search_keywords) if has_search_keywords else 0}",
                extra={
                    "user_id": user_id,
                    "has_interests": has_interests,
                    "has_behaviors": has_enough_behaviors,
                    "has_search_keywords": has_search_keywords,
                }
            )

            # Step 3: 判断推荐策略 - 有兴趣、足够行为或搜索关键词则进行个性化推荐
            if has_interests or has_enough_behaviors or has_search_keywords:
                # 个性化推荐
                products = await self._personalized_recommend_with_cache(
                    user_id=user_id,
                    grouped_behaviors=grouped_behaviors if has_enough_behaviors else None,
                    interests=interests.interests if has_interests else None,
                    search_keywords=search_keywords if has_search_keywords else None,
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
        grouped_behaviors: Optional[Dict[str, List]] = None,
        interests: Optional[Dict[str, str]] = None,
        search_keywords: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[ProductResponseDto]:
        """
        个性化推荐（支持基于兴趣、行为或搜索关键词），并缓存用户向量.

        Args:
            user_id: 用户ID
            grouped_behaviors: 分组的行为数据（view/purchase/search等）
            interests: 用户兴趣标签 (key: 英文code, value: 中文名称)
            search_keywords: 用户搜索关键词列表
            limit: 推荐数量

        Returns:
            推荐商品列表
            
        Note:
            - 只会过滤已购买（purchase）的商品
            - 其他行为（view/like/share/add_cart）的商品仍会被推荐
        """
        try:
            # 生成用户向量（融合行为、兴趣、搜索关键词）
            user_vector = await self._compute_user_vector(
                user_id=user_id,
                grouped_behaviors=grouped_behaviors,
                interests=interests,
                search_keywords=search_keywords,
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
        grouped_behaviors: Optional[Dict[str, List]] = None,
        interests: Optional[Dict[str, str]] = None,
        search_keywords: Optional[List[str]] = None,
    ) -> Optional[np.ndarray]:
        """
        计算用户向量（融合行为、兴趣、搜索关键词）.

        Args:
            user_id: 用户ID
            grouped_behaviors: 分组的行为数据（view/purchase/search等）
            interests: 用户兴趣标签
            search_keywords: 用户搜索关键词列表

        Returns:
            用户向量（numpy array），如果失败返回 None
            
        Note:
            - 商品行为向量权重 0.6，兴趣向量权重 0.4
            - 搜索关键词向量会被合并到最终结果中
        """
        try:
            # 第一步：生成商品行为向量（加权平均）
            behavior_vector = None
            if grouped_behaviors:
                # 计算有效行为数（所有有 target_id 的行为类型）
                behavior_count = sum(
                    len(grouped_behaviors.get(bt, [])) 
                    for bt in BEHAVIOR_TYPE_SURPORTED
                )
                # 如果有足够的行为数，则计算行为向量
                if behavior_count >= self.min_behavior_count:
                    behavior_vector = await self._get_user_vector_from_behaviors(grouped_behaviors)
                    if behavior_vector is not None:
                        logger.info(f"生成商品行为向量: user_id={user_id}, behavior_count={behavior_count}")
            
            # 第二步：生成兴趣向量
            interest_vector = None
            if interests:
                interest_vector = await self._get_user_vector_from_interests(interests)
                if interest_vector is not None:
                    logger.info(f"生成兴趣向量: user_id={user_id}, interest_count={len(interests)}")
            
            # 第三步：生成搜索关键词向量
            search_vector = None
            if search_keywords:
                search_vector = await self._get_user_vector_from_keywords(search_keywords)
                if search_vector is not None:
                    logger.info(f"生成搜索关键词向量: user_id={user_id}, keyword_count={len(search_keywords)}")
            
            # 第四步：融合向量
            # 4.1 融合商品行为向量和兴趣向量（行为权重稍高）
            base_vector = None
            strategies_used = []
            
            if behavior_vector is not None and interest_vector is not None:
                # 行为向量权重 0.6，兴趣向量权重 0.4
                base_vector = (
                    behavior_vector * VECTOR_FUSION_WEIGHTS["behavior"] + 
                    interest_vector * VECTOR_FUSION_WEIGHTS["interest"]
                )
                strategies_used.extend(["behavior", "interest"])
                logger.info(f"融合行为和兴趣向量: user_id={user_id}")
            elif behavior_vector is not None:
                base_vector = behavior_vector
                strategies_used.append("behavior")
            elif interest_vector is not None:
                base_vector = interest_vector
                strategies_used.append("interest")
            
            # 4.2 将搜索向量也纳入融合
            if base_vector is not None and search_vector is not None:
                # 搜索向量和基础向量取平均（搜索也很重要）
                user_vector = np.mean([base_vector, search_vector], axis=0)
                strategies_used.append("search")
                logger.info(f"融合搜索向量: user_id={user_id}")
            elif base_vector is not None:
                user_vector = base_vector
            elif search_vector is not None:
                user_vector = search_vector
                strategies_used.append("search")
            else:
                logger.warning(f"无法生成用户向量: user_id={user_id}")
                return None
            
            strategy_used = "+".join(strategies_used)
            logger.info(f"最终用户向量生成成功: user_id={user_id}, strategies={strategy_used}")
            
            return user_vector

        except Exception as e:
            logger.error(f"计算用户向量异常: user_id={user_id}, error={str(e)}", exc_info=True)
            return None

    async def _get_user_vector_from_behaviors(
        self, 
        grouped_behaviors: Dict[str, List]
    ) -> Optional[np.ndarray]:
        """
        根据用户分组的行为，生成用户向量（加权平均）.

        Args:
            grouped_behaviors: 分组的行为数据，包含所有行为类型：
                {
                    "purchase": [behavior1, ...],   # 购买
                    "add_cart": [behavior2, ...],   # 加入购物车
                    "like": [behavior3, ...],       # 点赞
                    "share": [behavior4, ...],      # 分享
                    "view": [behavior5, ...],       # 浏览
                    "search": [behavior6, ...],     # 搜索（无 target_id，不处理）
                }

        Returns:
            用户向量（numpy array），如果失败返回 None
            
        Note:
            - search 行为没有 target_id，只有 search_keyword，会在其他地方单独处理
            - 如果某些行为类型没有数据，会自动跳过
            - 如果同一商品有多个行为类型，取最大权重
        """
        try:
            collection = get_collection()
            collection.load()

            # 收集所有需要查询的商品ID，以及每种行为类型的统计
            all_product_ids = set()
            # 商品行为权重映射，因为 同一个用户对一件商品可能会有多种行为，比如 浏览后收藏、购买，这就是 3 个行为
            behavior_product_map = {}
            # {product_id: [(behavior_type, weight), ...]}
            # behavior_product_map = {
            #     product_id_A: [
            #         ("view", 1.0),      # 第一次浏览
            #         ("like", 2.0),      # 后来点赞
            #         ("add_cart", 2.5),  # 加入购物车
            #         ("purchase", 3.0)   # 最终购买
            #     ],
            #     product_id_B: [
            #         ("view", 1.0),      # 浏览
            #         ("share", 1.5)      # 分享
            #     ]
            # }

            behavior_stats = {bt: 0 for bt in BEHAVIOR_WEIGHTS.keys()}  # 统计每种行为的数量
            
            # 遍历所有有 target_id 的行为类型
            for behavior_type in BEHAVIOR_TYPE_SURPORTED:
                # 如果该行为类型在分组数据中存在
                if behavior_type in grouped_behaviors and grouped_behaviors[behavior_type]:
                    for behavior in grouped_behaviors[behavior_type]:
                        if behavior.target_id:
                            try:
                                product_id = int(behavior.target_id)
                                all_product_ids.add(product_id)
                                behavior_stats[behavior_type] += 1
                                
                                # 记录这个商品的行为类型和权重
                                if product_id not in behavior_product_map:
                                    behavior_product_map[product_id] = []
                                behavior_product_map[product_id].append(
                                    (behavior_type, BEHAVIOR_WEIGHTS.get(behavior_type, 1.0))
                                )
                            except (ValueError, TypeError):
                                logger.warning(f"无效的 target_id: {behavior.target_id}")
                                continue
            
            # 如果没有任何有效的商品ID，返回 None
            if not all_product_ids:
                logger.warning("没有有效的商品ID用于生成用户向量（所有行为类型都为空或无 target_id）")
                return None

            # 记录用户使用了哪些行为类型
            used_behaviors = [bt for bt, count in behavior_stats.items() if count > 0]
            logger.info(
                f"开始基于行为生成用户向量: "
                f"total_behaviors={sum(behavior_stats.values())}, "
                f"unique_products={len(all_product_ids)}, "
                f"behavior_breakdown={dict((bt, behavior_stats[bt]) for bt in used_behaviors)}"
            )

            # 从 Milvus 批量查询商品向量
            query_expr = f"product_id in {list(all_product_ids)}"
            results = collection.query(
                expr=query_expr,
                output_fields=["product_id", "embedding"]
            )

            if not results:
                logger.warning(f"未找到任何商品向量: product_ids={list(all_product_ids)}")
                return None

            # 提取向量并进行加权计算
            weighted_vectors = []
            total_weight = 0.0
            
            product_embeddings = {}
            for item in results:
                pid = item["product_id"]
                if pid not in product_embeddings:
                    product_embeddings[pid] = np.array(item["embedding"])
            
            # 对每个商品的向量应用权重
            for product_id, embedding in product_embeddings.items():
                if product_id in behavior_product_map:
                    # 如果同一个商品有多个行为，取最大权重，这样做是为了避免 同一件商品因为存在多个行为而计算多次，提高性能
                    max_weight = max(weight for _, weight in behavior_product_map[product_id])
                    weighted_vectors.append(embedding * max_weight)
                    total_weight += max_weight
            
            if not weighted_vectors or total_weight == 0:
                logger.warning("没有有效的加权向量")
                return None
            
            # 加权平均（100 件商品，就有 100 个加权后的向量，按列求和，total_weight = 100 就是取平均）
            user_vector = np.sum(weighted_vectors, axis=0) / total_weight

            logger.info(
                f"基于行为生成用户向量成功（加权平均）: "
                f"product_count={len(weighted_vectors)}, "
                f"total_weight={total_weight:.2f}, "
                f"vector_dim={len(user_vector)}, "
                f"used_behaviors={','.join(used_behaviors)}"
            )
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

    @deprecated("搜索接口弃用，搜索功能由商品服务主导")
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

            # 获取用户数据（兴趣、分组行为、搜索关键词）
            interests_task = self.user_client.get_user_interests(user_id)
            grouped_behaviors_task = self.user_client.get_user_behaviors_grouped(
                user_id, day=self.user_behavior_history
            )
            search_keywords_task = self.user_client.get_search_keywords(
                user_id, day=self.user_behavior_history
            )

            interests, grouped_behaviors, search_keywords = await asyncio.gather(
                interests_task, grouped_behaviors_task, search_keywords_task, 
                return_exceptions=True
            )

            # 检查是否有异常
            if isinstance(interests, Exception):
                logger.error(f"获取用户兴趣失败: user_id={user_id}, error={interests}")
                interests = None
            if isinstance(grouped_behaviors, Exception):
                logger.error(f"获取用户行为失败: user_id={user_id}, error={grouped_behaviors}")
                grouped_behaviors = {}
            if isinstance(search_keywords, Exception):
                logger.error(f"获取搜索关键词失败: user_id={user_id}, error={search_keywords}")
                search_keywords = []

            # 计算有效行为数（所有有 target_id 的行为类型）
            behavior_count = sum(
                len(grouped_behaviors.get(bt, [])) 
                for bt in BEHAVIOR_TYPE_SURPORTED
            ) if grouped_behaviors else 0

            has_interests = interests and interests.interests
            has_enough_behaviors = behavior_count >= self.min_behavior_count
            has_search_keywords = search_keywords and len(search_keywords) > 0

            # 只有当用户有数据时才更新向量
            if not (has_interests or has_enough_behaviors or has_search_keywords):
                logger.info(f"用户无有效数据，跳过刷新: user_id={user_id}")
                return

            # 计算用户向量（融合行为、兴趣、搜索关键词）
            user_vector = await self._compute_user_vector(
                user_id=user_id,
                grouped_behaviors=grouped_behaviors if has_enough_behaviors else None,
                interests=interests.interests if has_interests else None,
                search_keywords=search_keywords if has_search_keywords else None,
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

