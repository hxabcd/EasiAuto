"""基于 pyautogui 的登录基类：提供统一的输入/点击/按键与兼容模式处理

NOTE: pyautogui 必须延迟导入，在 QApplication 初始化之后再导入，否则会产生 COM 冲突。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import SupportsIndex, SupportsInt

from loguru import logger

from EasiAuto.core.display import Point, get_scale, get_screen_size_physical
from EasiAuto.models.config import config

from .base import BaseAutomator


class PyAutoGuiBaseAutomator(BaseAutomator):
    def __init__(self, account: str, password: str) -> None:
        super().__init__(account, password)

        self.compatibility_mode: bool = False
        screen_size = get_screen_size_physical()
        scale = get_scale()
        if config.Login.ForceCompatibilityMode:
            logger.warning("已强制启用兼容模式输入")
            self.compatibility_mode = True
        elif screen_size[1] / scale < 720:
            logger.info("检测到屏幕高度较低, 启用兼容模式输入")
            self.compatibility_mode = True

    def input(self, text: str, clear: bool = True, is_secret: bool = False):
        """统一输入函数"""
        import pyautogui
        import pyperclip

        if clear:
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")

        if is_secret:
            if (length := len(text)) > 2:  # noqa: SIM108
                log_text = text[0] + "*" * (length - 2) + text[-1]
            else:
                log_text = "*" * length
        else:
            log_text = text

        logger.debug(f"输入: {log_text}")
        if self.compatibility_mode:
            # 使用剪贴板输入，避免输入法遮挡等问题
            pyperclip.copy(text)
            pyperclip.paste()
        else:
            pyautogui.typewrite(text, interval=0.01)

    def click(
        self,
        x: SupportsInt | tuple[int, int] | Point,
        y: SupportsInt | None = None,
        *,
        clicks: SupportsIndex = 1,
        interval: float = 0,
        duration: float = 0,
    ):
        """统一点击函数"""
        import pyautogui

        if isinstance(x, SupportsInt):
            if y is None:
                raise ValueError("y坐标为空")
            _x, _y = int(x), int(y)
        elif isinstance(x, tuple):
            _x, _y = x
        elif isinstance(x, Point):
            _x, _y = x.x, x.y
        else:
            raise TypeError

        logger.debug(f"点击: ({_x}, {_y})")
        pyautogui.click(_x, _y, clicks=clicks, interval=interval, duration=duration)

    def press(self, keys: str | Iterable[str], presses: SupportsIndex = 1, interval: float = 0):
        """统一按键函数"""
        import pyautogui

        logger.debug(f"按下: {keys}")
        pyautogui.press(keys, presses, interval)
