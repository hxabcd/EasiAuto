from .automation.base import BaseAutomator
from .automation.cv import CVAutomator
from .automation.fixed import FixedAutomator
from .automation.inject import InjectAutomator
from .automation.uia import UIAAutomator

__all__ = [
    "BaseAutomator",
    "CVAutomator",
    "FixedAutomator",
    "InjectAutomator",
    "UIAAutomator",
]
