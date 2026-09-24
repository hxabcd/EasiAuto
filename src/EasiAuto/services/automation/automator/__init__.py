# NOTE: 所有实现中对 pyautogui 的导入必须使用延迟导入，在 QApplication 后初始化，否则会产生 COM 冲突

from .base import BaseAutomator
from .cv import CvAutomator
from .errors import LoginStatus
from .fixed import FixedAutomator
from .token import TokenAutomator
from .uia import UiaAutomator

__all__ = [
    "BaseAutomator",
    "CvAutomator",
    "FixedAutomator",
    "LoginStatus",
    "TokenAutomator",
    "UiaAutomator",
]
