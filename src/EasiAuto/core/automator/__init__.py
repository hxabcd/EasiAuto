# NOTE: 所有实现中对 pyautogui 的导入必须使用延迟导入，在 QApplication 后初始化，否则会产生 COM 冲突

from . import (
    cv,  # noqa: F401 触发注册
    fixed,  # noqa: F401 触发注册
    inject,  # noqa: F401 触发注册
    uia,  # noqa: F401 触发注册
)
from .base import BaseAutomator
from .registry import get_automator_class, register

__all__ = [
    "BaseAutomator",
    "get_automator_class",
    "register",
]
