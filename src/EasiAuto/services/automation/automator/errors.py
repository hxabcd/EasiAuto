"""自动化登录的异常与状态定义

与具体登录策略解耦，供 automator 各子类与调用方共用。
"""

from __future__ import annotations

from enum import Enum


class LoginCancelled(Exception):  # noqa: N818
    """登录被手动取消（或按配置跳过）"""


class LoginError(Exception):
    """登录异常"""

    def __init__(self, message: str, retry: bool = True) -> None:
        """
        Args:
            message (str): 异常信息
            retry (bool, optional): 是否允许错误重试
        """
        super().__init__(message)
        self.retry = retry


class LoginStatus(Enum):
    """登录流程的最终状态"""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
