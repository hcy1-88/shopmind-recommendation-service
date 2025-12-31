"""
@File       : settings.py
@Description:

@Time       : 2025/12/31 23:04
@Author     : hcy18
"""
"""Application settings and configuration management."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.utils.ip import get_local_ip

# 模块级别的单例实例（避免与 Pydantic 字段系统冲突）
_settings_instance: Optional["Settings"] = None


class Settings(BaseSettings):
    """对应.env中的配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="shopmind-recommendation-service", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Nacos Configuration
    nacos_server_addr: str = Field(
        default="127.0.0.1:8848",
        description="Nacos server address",
    )
    nacos_namespace: str = Field(
        default="public",
        description="Nacos namespace",
    )
    nacos_group: str = Field(
        default="DEFAULT_GROUP",
        description="Nacos group",
    )
    nacos_data_id: str = Field(
        default="shopmind-ai-service.yaml",
        description="Nacos config data ID",
    )
    nacos_username: Optional[str] = Field(
        default=None,
        description="Nacos username",
    )
    nacos_password: Optional[str] = Field(
        default=None,
        description="Nacos password",
    )

    # Service Registration
    service_name: str = Field(
        default="shopmind-recommendation-service",
        description="Service name for registration",
    )
    service_ip: str = Field(
        default_factory=get_local_ip, description="Service IP"
    )
    service_port: int = Field(
        default=8000,
        description="Service port",
    )
    service_cluster: str = Field(
        default="DEFAULT",
        description="Service cluster",
    )
    service_metadata: dict = Field(
        default_factory=lambda: {"version": "0.1.0"},
        description="Service metadata",
    )


    @classmethod
    def get_instance(cls) -> "Settings":
        """
        获取 Settings 单例实例.

        Returns:
            Settings 实例
        """
        global _settings_instance
        if _settings_instance is None:
            _settings_instance = cls()
        return _settings_instance



def get_settings() -> Settings:
    """
    获取 Settings 单例实例.

    Returns:
        Settings 单例实例
    """
    return Settings.get_instance()