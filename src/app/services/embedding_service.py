"""
@File       : embedding_service.py
@Description:

@Time       : 2025/12/31 23:52
@Author     : hcy18
"""
"""Embedding service for text and image embeddings."""

from typing import Optional

from app.config.nacos_client import get_nacos_client
from app.provider.embedding_model_provider import DashEmbeddingProvider, EmbeddingProvider
from app.utils.logger import app_logger as logger


class EmbeddingService:
    """嵌入服务，提供文本和图像的向量嵌入功能."""

    _instance: Optional["EmbeddingService"] = None

    def __init__(self):
        """Initialize embedding service."""
        self._provider: Optional[EmbeddingProvider] = None
        self._initialize()

    def _initialize(self) -> None:
        """Initialize embedding provider from config."""
        try:
            # 从 Nacos 获取配置
            nacos_client = get_nacos_client()
            config = nacos_client.get_config()

            # 获取 embedding 配置
            if "embedding" not in config:
                raise ValueError("Embedding 配置缺失")

            embedding_config = config["embedding"]
            provider_name = embedding_config.get("provider", "bailian")

            # 根据 provider 创建对应的实例
            if provider_name == "bailian":
                self._provider = DashEmbeddingProvider(embedding_config)
                logger.info(
                    f"Embedding service 初始化成功，Provider: {provider_name}, "
                    f"文本模型: {self._provider.text_model}, "
                    f"维度: {self._provider.text_model_dim}"
                )
            else:
                raise ValueError(f"不支持的 embedding provider: {provider_name}")

        except Exception as e:
            logger.error(f"Embedding service 初始化失败: {e}", exc_info=True)
            raise

    @property
    def provider(self) -> EmbeddingProvider:
        """Get embedding provider."""
        if self._provider is None:
            raise RuntimeError("Embedding provider 未初始化")
        return self._provider

    @property
    def text_model_dim(self) -> int:
        """Get text model dimension."""
        return self.provider.text_model_dim

    @property
    def vision_model_dim(self) -> int:
        """Get vision model dimension."""
        return self.provider.vision_model_dim

    async def embed_text(self, text: str) -> list[float]:
        """
        嵌入单个文本.

        Args:
            text: 要嵌入的文本

        Returns:
            向量表示
        """
        return await self.provider.embed_document(text)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        批量嵌入文本.

        Args:
            texts: 文本列表

        Returns:
            向量列表
        """
        return await self.provider.embed_documents(texts)

    async def embed_query(self, query: str) -> list[float]:
        """
        嵌入查询文本（用于搜索）.

        Args:
            query: 查询文本

        Returns:
            向量表示
        """
        return await self.provider.embed_query(query)

    async def embed_image(self, image: str) -> list[float]:
        """
        嵌入单张图片.

        Args:
            image: 图片 URL 或 Base64

        Returns:
            向量表示
        """
        return await self.provider.embed_image(image)

    async def embed_images(self, images: list[str]) -> list[list[float]]:
        """
        批量嵌入图片.

        Args:
            images: 图片 URL 或 Base64 列表

        Returns:
            向量列表
        """
        return await self.provider.embed_images(images)

    @classmethod
    def get_instance(cls) -> "EmbeddingService":
        """
        获取 EmbeddingService 单例.

        Returns:
            EmbeddingService 实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def get_embedding_service() -> EmbeddingService:
    """获取 embedding service 单例（便捷函数）."""
    return EmbeddingService.get_instance()


def init_embedding_service() -> None:
    embedding_service = get_embedding_service()
    logger.info("Embedding service 初始化成功，文本模型维度：%d", embedding_service.text_model_dim)