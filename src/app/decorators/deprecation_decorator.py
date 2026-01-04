"""
@File       : deprecation_decorator.py
@Description:

@Time       : 2026/1/4 6:09
@Author     : hcy18
"""
import warnings
from functools import wraps


def deprecated(reason: str = "This function is deprecated."):
    """
    装饰器：标记函数为废弃，并在调用时发出警告。

    :param reason: 废弃原因或替代建议
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(
                f"{func.__name__} is deprecated. {reason}",
                DeprecationWarning,
                stacklevel=2
            )
            return func(*args, **kwargs)

        return wrapper

    return decorator