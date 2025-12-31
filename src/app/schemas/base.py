"""
@File       : base.py
@Description: Pydantic 基类模块，提供自动驼峰命名转换功能.

@Time       : 2025/12/31 23:59
@Author     : hcy18
"""
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelCaseModel(BaseModel):
    """
    自动转换驼峰命名的 Pydantic 基类.

    特性：
    - Python 代码中使用蛇形命名（snake_case），符合 PEP 8 规范
    - JSON 序列化/反序列化时自动转换为驼峰命名（camelCase）
    - 与前端 JavaScript、后端 Java 服务无缝对接
    - 支持同时接受蛇形和驼峰命名（populate_by_name=True）

    示例：
        ```python
        class UserRequest(CamelCaseModel):
            user_name: str  # Python 中使用蛇形命名
            image_url: str

        # 前端发送的 JSON：{"userName": "张三", "imageUrl": "http://..."}
        # Python 中访问：request.user_name, request.image_url
        # 返回的 JSON：{"userName": "张三", "imageUrl": "http://..."}
        ```
    """

    model_config = ConfigDict(
        alias_generator=to_camel,     # 自动转换为驼峰命名
        populate_by_name=True,         # 允许同时使用蛇形和驼峰命名
    )