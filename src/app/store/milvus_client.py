"""
@File       : milvus_client.py
@Description:

@Time       : 2025/12/31 23:12
@Author     : hcy18
"""
from typing import Optional

from pymilvus import connections, MilvusClient as PyMilvusClient, utility, MilvusException

from app.config.nacos_client import get_nacos_client
from app.store.product_collection import check_product_collection
from app.utils.logger import app_logger as logger


class MilvusClient:
    """Milvus vector database client wrapper."""

    _instance: Optional["MilvusClient"] = None

    def __init__(self):
        """Initialize Milvus client."""
        self._config = None
        self.client: Optional[PyMilvusClient] = None
        self._initialized = False

    def _initialize(self) -> None:
        """Initialize Milvus client."""
        if self._initialized:
            logger.info("Milvus client 已初始化，跳过重复初始化")
            return

        try:
            # 1. 从 nacos 获取 milvus 配置
            nacos_client = get_nacos_client()
            self._config = nacos_client.get_milvus_config()

            logger.info(
                f"Milvus 配置: host={self._config.get('host')}, "
                f"port={self._config.get('port')}, "
                f"db_name={self._config.get('db_name')}"
            )

            # 2. 构建 Milvus 客户端连接参数
            uri = f"http://{self._config['host']}:{self._config['port']}"
            token = self._config.get('token', 'root:Milvus')  # 默认 token

            # 3. 创建 MilvusClient 实例
            self.client = PyMilvusClient(
                uri=uri,
                token=token,
            )

            logger.info("Milvus client 连接成功")

            # 4. 切换数据库
            database_name = str(self._config["db_name"])

            # 切换到指定数据库
            try:
                self.client.using_database(database_name)
            except MilvusException as e:
                if e.code == 37:  # DatabaseNotExist 错误码
                    logger.error(f"指定的数据库{database_name}不存在!")
                raise

            logger.info(f"已切换到数据库: {database_name}")

            # 5. 使用传统连接方式（用于 Collection 操作）
            connections.connect(
                alias="default",
                host=self._config['host'],
                port=str(self._config['port']),
                user="root",  # 从 token 中提取
                password=token.split(':')[1] if ':' in token else 'Milvus',
                db_name=database_name,
            )
            logger.info("Pymilvus connections 连接成功")

            # 6. 初始化 product collection
            logger.info("开始初始化 product collection")
            check_product_collection(database_name)
            logger.info("Product collection 初始化完成")

            self._initialized = True
            logger.info("Milvus client 初始化成功")

        except Exception as e:
            logger.error(f"Milvus 初始化失败: {e}", exc_info=True)
            raise

    def ensure_initialized(self) -> None:
        """确保 client 已初始化."""
        if not self._initialized:
            self._initialize()

    @classmethod
    def get_instance(cls) -> "MilvusClient":
        """
        获取 MilvusClient 单例.

        Returns:
            MilvusClient 实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def close(self) -> None:
        """关闭 Milvus 连接."""
        try:
            if self.client:
                self.client.close()
                logger.info("Milvus client 连接已关闭")

            # 断开 pymilvus connections
            if connections.has_connection("default"):
                connections.disconnect("default")
                logger.info("Pymilvus connections 已断开")

            self._initialized = False

        except Exception as e:
            logger.error(f"关闭 Milvus 连接失败: {e}", exc_info=True)


def get_milvus_client() -> MilvusClient:
    """获取 Milvus client 单例（便捷函数）."""
    client = MilvusClient.get_instance()
    client.ensure_initialized()
    return client


def init_milvus() -> None:
    get_milvus_client()
    logger.info("Milvus 初始化成功")