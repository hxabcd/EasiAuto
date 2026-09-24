"""窗口查找与激活。"""

from __future__ import annotations

import pywintypes
import win32api
import win32con
import win32gui
from loguru import logger


def switch_window(hwnd: int, press_key: bool = False) -> bool:
    """将窗口切到前台并激活"""
    try:
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
        if win32gui.GetForegroundWindow() == hwnd:
            return True

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)

        if win32gui.GetForegroundWindow() == hwnd:
            return True
        if press_key:  # 模拟 Alt 键以确保系统标记当前为交互状态
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32gui.SetForegroundWindow(hwnd)
            return win32gui.GetForegroundWindow() == hwnd
        return False
    except pywintypes.error as e:
        logger.error(f"切换窗口焦点时发生异常: {e}")
        return False


def enum_windows() -> list[tuple[int, str, str]]:
    """枚举顶层窗口

    Returns:
        list[tuple[int, str, str]]: (句柄, 标题, 类名) 列表；
        仅包含有标题的窗口，以及类名含 easinote 的无标题窗口
    """

    def callback(hwnd, windows):
        window_text = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd) or ""
        if window_text or "easinote" in class_name.lower():
            windows.append((hwnd, window_text, class_name))
        return True

    windows: list[tuple[int, str, str]] = []
    win32gui.EnumWindows(callback, windows)

    return windows


def log_windows() -> None:
    """把所有顶层窗口打印到调试日志，供排查窗口定位问题"""
    windows = enum_windows()
    windows.sort(key=lambda x: x[1])

    logger.debug("==========当前窗口==========")
    for hwnd, text, class_name in windows:
        logger.debug(f"句柄: {hwnd:8x} | 标题: {text[:30]:30} | 类名: {class_name}")


def find_window(title: str, *, substring: bool = False) -> int:
    """按标题查找窗口句柄

    Args:
        title (str): 目标窗口标题
        substring (bool, optional): 为 True 时按包含匹配（用于精确标题匹配失败的场景）

    Returns:
        int: 窗口句柄，未找到时为 0
    """
    if not substring:
        return win32gui.FindWindow(None, title) or 0

    for hwnd, text, _ in enum_windows():
        if title in text:
            return hwnd
    return 0
