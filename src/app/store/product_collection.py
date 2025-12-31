"""
@File       : product_collection.py
@Description:

@Time       : 2025/12/31 23:18
@Author     : hcy18
"""
from pymilvus import Collection
from pymilvus.orm import utility

from app.utils.logger import app_logger as logger

COLLECTION_NAME = "product_collection"

def check_product_collection(db_name: str) -> None:
    """
    初始化 product collection（创建或加载）.

    Returns:
        Collection 实例
    """
    # 检查 collection 是否已存在
    if utility.has_collection(COLLECTION_NAME):
        logger.info(f"Collection '{COLLECTION_NAME}' 已存在，加载现有 collection")
    else:
        raise RuntimeError(f"milvus 中,数据库 {db_name} 下 {COLLECTION_NAME} collection 不存在！")


def get_collection() -> Collection:
    return Collection(name=COLLECTION_NAME)