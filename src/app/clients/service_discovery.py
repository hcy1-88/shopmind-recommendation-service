"""
@File       : service_discovery.py
@Description: Service discovery client for getting service addresses from Nacos

@Time       : 2026/01/01
@Author     : hcy18
"""
from typing import Optional
from v2.nacos import SelectInstancesParam

from app.config.nacos_client import get_nacos_client
from app.utils.logger import app_logger as logger


class ServiceDiscovery:
    """服务发现客户端，用于从 Nacos 获取其他微服务的地址."""

    @staticmethod
    async def get_service_url(service_name: str, group_name: str = "DEFAULT_GROUP") -> str:
        """
        从 Nacos 获取服务地址.

        Args:
            service_name: 服务名称（如 shopmind-user-service）
            group_name: 服务组名，默认 DEFAULT_GROUP

        Returns:
            服务的 HTTP URL（如 http://192.168.1.100:8080）

        Raises:
            RuntimeError: 如果服务未找到或不健康
        """
        try:
            nacos_client = get_nacos_client()
            register_client = nacos_client.register_client

            if not register_client:
                raise RuntimeError("Nacos 注册中心客户端未初始化")

            # 获取健康的服务实例
            instances = await register_client.select_instances(
                SelectInstancesParam(
                    service_name=service_name,
                    group_name=group_name,
                    healthy_only=True,
                )
            )

            if not instances or len(instances) == 0:
                raise RuntimeError(f"未找到健康的服务实例: {service_name}")

            # 选择第一个健康的实例（简单负载均衡）
            instance = instances[0]
            service_url = f"http://{instance.ip}:{instance.port}"

            logger.info(
                f"获取服务地址成功: {service_name} -> {service_url}",
                extra={"service_name": service_name, "url": service_url}
            )

            return service_url

        except Exception as e:
            logger.error(
                f"获取服务地址失败: {service_name}",
                extra={"service_name": service_name, "error": str(e)},
                exc_info=True
            )
            raise RuntimeError(f"无法获取服务 {service_name} 的地址: {str(e)}")


# 便捷函数
async def get_user_service_url() -> str:
    """获取用户服务的 URL."""
    return await ServiceDiscovery.get_service_url("shopmind-user-service")


async def get_product_service_url() -> str:
    """获取商品服务的 URL."""
    return await ServiceDiscovery.get_service_url("shopmind-product-service")

