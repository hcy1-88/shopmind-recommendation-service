"""Redis client for caching user vectors."""

import json
from typing import Optional
import redis.asyncio as aioredis

from app.config.nacos_client import get_nacos_client
from app.utils.logger import app_logger as logger


class RedisClient:
    """Redis client wrapper for user vector caching."""

    _instance: Optional["RedisClient"] = None

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.prefix = "user_vector:"
        self.ttl = 3600  # 默认 1 小时过期

    @classmethod
    def get_instance(cls) -> "RedisClient":
        """获取 Redis 客户端单例."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def connect(self):
        """连接 Redis."""
        try:
            nacos_client = get_nacos_client()
            redis_config = nacos_client.get_redis_config()
            
            # 构建连接参数
            connect_params = {
                "password": redis_config.get("password"),
                "encoding": "utf-8",
                "decode_responses": True,
                "max_connections": redis_config.get("max_connections", 10),
            }
            
            self.redis = await aioredis.from_url(
                redis_config["url"],
                **connect_params
            )

            # 测试连接
            await self.redis.ping()
            logger.info("Redis 连接成功")

        except Exception as e:
            logger.error(f"Redis 连接失败: {e}", exc_info=True)
            raise

    async def close(self):
        """关闭 Redis 连接."""
        if self.redis:
            await self.redis.close()
            logger.info("Redis 连接已关闭")

    async def get_user_vector(self, user_id: int) -> Optional[list[float]]:
        """
        获取用户向量.

        Args:
            user_id: 用户ID

        Returns:
            用户向量（list[float]），如果不存在返回 None
        """
        try:
            key = f"{self.prefix}{user_id}"
            value = await self.redis.get(key)

            if value:
                vector = json.loads(value)
                logger.info(f"从 Redis 获取用户向量: user_id={user_id}, dim={len(vector)}")
                return vector
            else:
                logger.info(f"Redis 中不存在用户向量: user_id={user_id}")
                return None

        except Exception as e:
            logger.error(f"从 Redis 获取用户向量失败: user_id={user_id}, error={e}", exc_info=True)
            return None

    async def set_user_vector(self, user_id: int, vector: list[float], ttl: Optional[int] = None):
        """
        保存用户向量到 Redis.

        Args:
            user_id: 用户ID
            vector: 用户向量
            ttl: 过期时间（秒），如果为 None 则使用默认值
        """
        try:
            key = f"{self.prefix}{user_id}"
            value = json.dumps(vector)
            expire = ttl if ttl is not None else self.ttl

            await self.redis.setex(key, expire, value)
            logger.info(f"保存用户向量到 Redis: user_id={user_id}, dim={len(vector)}, ttl={expire}s")

        except Exception as e:
            logger.error(f"保存用户向量到 Redis 失败: user_id={user_id}, error={e}", exc_info=True)

    async def delete_user_vector(self, user_id: int):
        """
        删除用户向量.

        Args:
            user_id: 用户ID
        """
        try:
            key = f"{self.prefix}{user_id}"
            await self.redis.delete(key)
            logger.info(f"删除用户向量: user_id={user_id}")

        except Exception as e:
            logger.error(f"删除用户向量失败: user_id={user_id}, error={e}", exc_info=True)

    async def exists_user_vector(self, user_id: int) -> bool:
        """
        检查用户向量是否存在.

        Args:
            user_id: 用户ID

        Returns:
            是否存在
        """
        try:
            key = f"{self.prefix}{user_id}"
            return await self.redis.exists(key) > 0

        except Exception as e:
            logger.error(f"检查用户向量失败: user_id={user_id}, error={e}", exc_info=True)
            return False


def get_redis_client() -> RedisClient:
    """获取 Redis 客户端单例."""
    return RedisClient.get_instance()

