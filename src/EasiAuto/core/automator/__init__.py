# NOTE: 所有实现中对 pyautogui 的导入必须使用延迟导入，在 QApplication 后初始化，否则会产生 COM 冲突

from .base import BaseAutomator
from .cv import CVAutomator
from .fixed import FixedAutomator
from .inject import InjectAutomator
from .uia import UIAAutomator

__all__ = [
    "BaseAutomator",
    "CVAutomator",
    "FixedAutomator",
    "InjectAutomator",
    "UIAAutomator",
]
