"""
@File       : nacos_client.py
@Description:

@Time       : 2025/12/31 23:10
@Author     : hcy18
"""
"""Nacos client for service discovery and configuration management."""

import yaml
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Any, Optional

from v2.nacos import ClientConfigBuilder, GRPCConfig, NacosConfigService, NacosNamingService, ClientConfig, ConfigParam, \
    RegisterInstanceParam, DeregisterInstanceParam

from app.config.settings import Settings, get_settings
from app.utils.logger import app_logger as logger


class NacosClient:
    """Nacos client wrapper for service registration and configuration."""

    _instance: Optional["NacosClient"] = None

    def __init__(self, settings: Settings):
        """
        Initialize Nacos client.

        Args:
            settings: Application settings
        """
        self.settings: Settings = settings
        """nacos 配置信息"""
        self.addr: str = settings.nacos_server_addr
        self.nacos_user: str = settings.nacos_username or ""
        self.nacos_password: str = settings.nacos_password or ""
        self.namespace: str = settings.nacos_namespace
        self.data_id: str = settings.nacos_data_id
        self.group: str = settings.nacos_group
        self.log_level: str = settings.log_level
        self.service_name: str = settings.service_name
        self.service_ip: str = settings.service_ip
        self.service_port: int = settings.service_port
        self.service_cluster: str = settings.service_cluster
        self.service_metadata: dict = settings.service_metadata
        # nacos 配置对象和客户端对象
        self.client_config: ClientConfig | None = None
        self.config_client: NacosConfigService | None = None
        self.register_client: NacosNamingService | None = None
        self.config_from_nacos: dict[str, Any] | None = None

    @classmethod
    def get_instance(cls, settings: Optional[Settings] = None) -> "NacosClient":
        """
        获取 NacosClient 单例实例.

        Args:
            settings: 应用配置，如果为 None 则使用默认配置。
                      仅在第一次调用时生效，后续调用会忽略此参数。

        Returns:
            NacosClient 单例实例
        """
        if cls._instance is None:
            if settings is None:
                settings = get_settings()
            cls._instance = cls(settings=settings)
        return cls._instance

    async def config_listener(self, tenant, data_id, group, content) -> None:
        """监听器：监听配置"""
        logger.info(
            "Configuration updated 配置变更",
            extra={
                "data_id": data_id,
                "group": group,
                "content": content,
            }
        )
        self.config_from_nacos = yaml.safe_load(content)


    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def connect(self) -> None:
        """Nacos 连接入口，连接并注册服务"""
        try:
            self.client_config = (ClientConfigBuilder()
                                  .server_address(self.addr)
                                  .namespace_id(self.namespace)
                                  .username(self.nacos_user)
                                  .password(self.nacos_password)
                                  .log_level('INFO')
                                  .grpc_config(GRPCConfig(grpc_timeout=5000))
                                  .build())
            # 配置中心客户端
            self.config_client = await NacosConfigService.create_config_service(self.client_config)
            await self.config_client.add_listener(data_id=self.data_id, group=self.group, listener=self.config_listener)
            # 注册中心客户端
            self.register_client = await NacosNamingService.create_naming_service(self.client_config)
            # 连接
            await self.init_config_center()
            await self.init_register_center()
            logger.info(
                "------------- 连接 Nacos server 完毕！",
                extra={
                    "server": self.service_name,
                    "namespace": self.namespace,
                },
            )
        except Exception as e:
            logger.error(f"Failed to connect to Nacos: {e}")
            raise


    async def init_config_center(self):
        """初始化配置中心"""
        if not self.config_client:
            raise RuntimeError("nacos 配置中心客户端未建立！")
        # 获取配置
        content = await self.config_client.get_config(ConfigParam(
            data_id=self.data_id,
            group=self.group,
        ))
        logger.info("Nacos 配置中心已连接！")
        # 转 yaml
        self.config_from_nacos = yaml.safe_load(content)
        # 验证配置是否成功设置
        if self.config_from_nacos is None:
            logger.error(
                "警告：Nacos 配置解析后为 None，将使用空字典",
                extra={"content": content[:500] if content else "None"},
            )
            self.config_from_nacos = {}
        logger.info("Nacos 配置获取如下：", extra={"config": self.config_from_nacos})


    async def init_register_center(self) -> None:
        """注册服务实例到 Nacos."""
        if not self.register_client:
            raise RuntimeError("nacos 注册中心客户端未建立！")

        try:
            await self.register_client.register_instance(
                request=RegisterInstanceParam(service_name=self.service_name, group_name=self.group, ip=self.service_ip,
                                              port=self.service_port, weight=1.0, cluster_name=self.service_cluster, metadata=self.service_metadata,
                                              enabled=True,
                                              healthy=True, ephemeral=True))
            logger.info(
                "服务已成功注册到了 Nacos ！",
                extra={
                    "service_name": self.service_name,
                    "ip": self.service_ip,
                    "port": self.service_port,
                },
            )
        except Exception as e:
            logger.error(f"Failed to register service: {e}")
            raise


    async def deregister_service(self) -> None:
        """从 Nacos 注销."""
        try:
            await self.config_client.shutdown()
            await self.register_client.deregister_instance(
                request=DeregisterInstanceParam(service_name=self.service_name, group_name=self.group, ip=self.service_ip,
                                                port=self.service_port, cluster_name=self.service_cluster, ephemeral=True)
            )
            logger.info(
                "服务已从 nacos 注销！",
                extra={"service_name": self.settings.service_name},
            )
        except Exception as e:
            logger.error(f"Failed to deregister service: {e}")

    def get_config(self,) -> dict[str, Any]:
        """
        获取配置（字典形式）
        """
        return self.config_from_nacos


    def get_milvus_config(self) -> dict[str, Any]:
        """
        获取 Milvus 配置. 优先从 nacos，若无则从 settings，也就是 .env

        Returns:
            Milvus configuration
        """
        nacos_config = self.config_from_nacos
        NAME = "milvus"
        if NAME in nacos_config:
            return nacos_config[NAME]
        raise ValueError("Milvus 配置项缺失，服务启动失败！")


    def get_embedding_config(self) -> dict[str, Any]:
        """获取嵌入模型的配置"""
        nacos_config = self.config_from_nacos
        NAME = "embedding"
        if NAME in nacos_config:
            return nacos_config[NAME]
        raise ValueError("嵌入模型 配置缺失，服务启动失败！")


    def get_recommendation_config(self) -> dict[str, Any]:
        """跟推荐相关的参数"""
        nacos_config = self.config_from_nacos
        NAME = "recommendation"
        if NAME in nacos_config:
            return nacos_config[NAME]
        raise ValueError("recommendation 配置项缺失，服务启动失败！")


def get_nacos_client(settings: Optional[Settings] = None) -> NacosClient:
    """
    获取 NacosClient 单例实例.

    Args:
        settings: 应用配置，如果为 None 则使用默认配置。
                  仅在第一次调用时生效，后续调用会忽略此参数。

    Returns:
        NacosClient 单例实例
    """
    return NacosClient.get_instance(settings=settings)


async def init_nacos(settings: Settings):
    nacos_client = get_nacos_client(settings)
    await nacos_client.connect()