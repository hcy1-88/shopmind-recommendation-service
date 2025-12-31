"""
@File       : embedding_model_provider.py
@Description:

@Time       : 2025/12/31 23:26
@Author     : hcy18
"""
"""
@File       : embedding_model_provider.py
@Description:

@Time       : 2025/12/29 18:40
@Author     : hcy18
"""
from abc import ABC, abstractmethod
from typing import Any

import dashscope
from langchain_community.embeddings import DashScopeEmbeddings


class EmbeddingProvider(ABC):
    """嵌入模型"""

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """嵌入查询"""
        pass

    @abstractmethod
    async def embed_document(self, text: str) -> list[float]:
        """嵌入单一文本"""
        pass

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """嵌入多个文本"""
        pass

    @abstractmethod
    async def embed_image(self, image: str) -> list[float]:
        """嵌入一张图片"""
        pass

    @abstractmethod
    async def embed_images(self, images: list[str]) -> list[list[float]]:
        """嵌入多张图片"""
        pass

class DashEmbeddingProvider(EmbeddingProvider):

    @property
    def provider_name(self) -> str:
        return "bailian"

    def __init__(self, config: dict[str, Any]):
        bailian_config = config[self.provider_name]
        self.text_model = bailian_config["text_model"]
        self.text_model_dim = bailian_config["text_model_dim"]
        self.vision_model = bailian_config["vision_model"]
        self.vision_model_dim = bailian_config["vision_model_dim"]
        self.api_key = bailian_config["api_key"]
        self.text_embeddings = DashScopeEmbeddings(model=self.text_model, dashscope_api_key=self.api_key)

    async def embed_query(self, query: str) -> list[float]:
        """适用于对查询进行嵌入"""
        if not query:
            return []
        return await self.text_embeddings.aembed_query(text=query)

    async def embed_document(self, text: str) -> list[float]:
        """对单一文档进行嵌入，适合存放到向量数据库中被检索"""
        if not text:
            return []
        response =  await self.text_embeddings.aembed_documents([text])
        return response[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文档的嵌入，适合存放到向量数据库中被检索"""
        if not texts:
            return []
        return await self.text_embeddings.aembed_documents(texts)

    async def embed_image(self, image: str) -> list[float]:
        """一张图片的嵌入"""
        if not image:
            return []
        input = [{'image': image}]
        response = dashscope.MultiModalEmbedding.call(model=self.vision_model, api_key=self.api_key, input=input, dimension=self.vision_model_dim)
        return response.output['embeddings'][0]['embedding']

    async def embed_images(self, images: list[str]) -> list[list[float]]:
        """
        批量图像嵌入（推荐使用此方法提高效率）

        Args:
            images: 图像 URL 或 Base64 编码字符串列表（DashScope 支持这两种格式）

        Returns:
            List of embeddings, each is a list of floats.
        """
        if not images:
            return []

        # 构造批量输入
        input_data = [{'image': img} for img in images]

        response = dashscope.MultiModalEmbedding.call(
            model=self.vision_model,
            api_key=self.api_key,
            input=input_data,
            dimension=self.vision_model_dim
        )

        if not response.output:
            raise RuntimeError(f"DashScope API error: {response.code} - {response.message}")

        # 按顺序提取嵌入向量
        embeddings = [item['embedding'] for item in response.output['embeddings']]
        return embeddings

