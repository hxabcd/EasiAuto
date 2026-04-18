from __future__ import annotations

import os
import signal
import sys
from abc import ABCMeta
from pathlib import Path
from typing import NoReturn, cast

import psutil
import pywintypes
import win32api
import win32com.client
import win32con
import win32gui
import win32process
from loguru import logger

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

from EasiAuto.common.consts import (
    EA_BASEDIR,
    EA_EXECUTABLE,
    EA_RESDIR,
)


def get_resource(filename: str):
    """获取资源路径"""
    return str(EA_RESDIR / filename)


def get_scale() -> float:
    """获取当前系统缩放比例"""
    app = cast(QApplication, QApplication.instance())
    if app is None:
        raise RuntimeError("QApplication 未初始化")
    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("无法获取主屏幕信息")
    return screen.devicePixelRatio()


def get_screen_size() -> tuple[int, int]:
    """获取屏幕尺寸（逻辑坐标）"""
    app = cast(QApplication, QApplication.instance())
    if app is None:
        raise RuntimeError("QApplication 未初始化")
    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("无法获取主屏幕信息")

    geo = screen.geometry()
    return (geo.width(), geo.height())


def get_screen_size_physical() -> tuple[int, int]:
    """获取屏幕尺寸（物理像素）"""
    w, h = get_screen_size()
    scale = get_scale()
    return (int(w * scale), int(h * scale))


class Point:
    """一个点，描述屏幕上的坐标。坐标值恒为整数"""

    scale: float | None = None

    def __init__(self, x: int | float | tuple[int | float, int | float], y: int | float | None = None):
        if isinstance(x, tuple):
            x_val, y_val = x
        else:
            if y is None:
                raise ValueError("必须传入 y 坐标或一个二元组")
            x_val, y_val = x, y

        if x_val < 0 or y_val < 0:
            raise ValueError("坐标值必须为非负数")

        self.x: int = int(x_val)
        self.y: int = int(y_val)

    def __add__(self, other: Point) -> Point:
        if not isinstance(other, Point):
            return NotImplemented
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Point) -> Point:
        if not isinstance(other, Point):
            return NotImplemented
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, other: int | float) -> Point:
        if not isinstance(other, (int, float)):
            return NotImplemented
        return Point(self.x * other, self.y * other)

    def __rmul__(self, other: int | float) -> Point:
        return self.__mul__(other)

    def __truediv__(self, other: int | float) -> Point:
        return self.__mul__(1 / other)

    def scaled(self) -> Point:
        """获取缩放后的坐标"""
        if Point.scale is None:
            Point.scale = get_scale()
        return Point(self.x * Point.scale, self.y * Point.scale)


def calc_relative_login_window_position(
    position: Point, window_size: tuple[int, int], base_size: tuple[int, int]
) -> Point:
    """计算相对登录窗口的位置

    Args:
        position (Point): 原始位置
        window_size (tuple[int, int]): 窗口大小
        base_size (tuple[int, int]): 原始位置与窗口大小所基于的屏幕分辨率
    """

    screen = Point(get_screen_size_physical())
    base_screen = Point(base_size)
    window = Point(window_size)
    window_position = (base_screen - window) / 2

    rel_position = position - window_position
    scaled_rel_position = rel_position.scaled()
    scaled_top_left = (screen - window.scaled()) / 2
    return scaled_rel_position + scaled_top_left


class QABCMeta(type(QObject), ABCMeta):  # type: ignore
    """QObject 与抽象基类的兼容元类"""


def create_shortcut(args: str, name: str, show_result_to: QWidget | None = None):
    """创建 EasiAuto 桌面快捷方式"""
    try:
        name = name + ".lnk"

        logger.info(f"在桌面创建快捷方式: {name}")

        shell = win32com.client.Dispatch("WScript.Shell")
        desktop_path = Path(shell.SpecialFolders("Desktop"))
        shortcut_path = desktop_path / name

        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = str(EA_EXECUTABLE)
        shortcut.Arguments = args
        shortcut.WorkingDirectory = str(EA_BASEDIR)
        shortcut.IconLocation = get_resource("icons/EasiAutoShortcut.ico")
        shortcut.Save()

        logger.success("创建成功")
        if show_result_to:
            InfoBar.success(
                title="成功",
                content=f"已在桌面创建 {name}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=show_result_to,
            )
    except Exception as e:
        logger.error(f"创建快捷方式失败: {e}")
        if show_result_to:
            InfoBar.error(
                title="创建失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=show_result_to,
            )


def switch_window(hwnd: int, press_key: bool = True):
    """通过句柄切换焦点"""
    try:
        if win32gui.GetForegroundWindow() == hwnd:
            return True

        # 强制恢复并显示
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        if win32gui.GetForegroundWindow() == hwnd:
            return True

        if press_key:  # 模拟 Alt 键以确保系统标记当前为交互状态
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.SetForegroundWindow(hwnd)

        return True
    except pywintypes.error as e:
        logger.warning(f"切换窗口焦点失败: {e}")
        return False


def get_window_by_title(title: str):
    """通过标题获取窗口"""

    def callback(hwnd, extra):
        if title in win32gui.GetWindowText(hwnd):
            extra.append(hwnd)

    hwnds = []
    # 枚举所有顶层窗口
    win32gui.EnumWindows(callback, hwnds)

    if hwnds:
        logger.success(f"已找到标题包含 '{title}' 的窗口")
        return hwnds
    logger.warning(f"未找到标题包含 '{title}' 的窗口")
    return None


def get_window_by_pid(pid: int, target_title: str, strict: bool = True) -> int | None:
    """根据进程 PID 查找窗口句柄，支持部分标题匹配"""
    hwnd_found = None

    def callback(hwnd, _):
        nonlocal hwnd_found
        _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
        if window_pid == pid:
            window_title = win32gui.GetWindowText(hwnd)
            if (target_title == window_title) if strict else (target_title in window_title):
                hwnd_found = hwnd
                return False  # 找到就停止枚举
        return True

    win32gui.EnumWindows(callback, None)
    return hwnd_found

def kill_process(name: str, force: bool = False, wait: bool = False, timeout: float = 1.0) -> None:
    """终止进程

    Args:
        name (str): 进程名
        force (bool, optional): 强制终止进程
        wait (bool, optional): 等待进程结束（阻塞）
    """
    for process in psutil.process_iter(["name"]):
        if process.info["name"] == f"{name}.exe":
            try:
                if force:
                    process.kill()
                else:
                    process.terminate()
                logger.info(f"已向进程 {name} 发送{'强行' if force else ''}终止信号{', 等待中……' if wait else ''}")

                try:
                    process.wait(timeout)
                    logger.info(f"成功关闭进程 {name}")
                except psutil.TimeoutExpired:
                    logger.warning(f"进程 {name} 关闭超时")
            except psutil.NoSuchProcess:
                logger.warning(f"进程 {name} 已不存在")
            except psutil.AccessDenied:
                logger.warning("访问被拒绝, 回退至 taskkill")
                if force:
                    os.system(f'taskkill /f /im "{name}.exe" >nul 2>&1')
                else:
                    os.system(f'taskkill /im "{name}.exe" >nul 2>&1')

def get_ci_executable() -> Path | None:
    """获取 ClassIsland 可执行文件位置"""
    try:
        lnk_path = Path(
            os.path.expandvars(
                r"%USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ClassIsland.lnk"
            )
        ).resolve()

        if not lnk_path.exists():
            return None

        # 解析快捷方式
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(lnk_path))
        target = shortcut.TargetPath

        return Path(target).resolve()

    except Exception as e:
        logger.error(f"获取 ClassIsland 路径时出错: {e}")
        return None


def init_exit_signal_handlers() -> None:
    """退出信号处理器"""

    def signal_handler(signum, _):
        logger.debug(f"收到信号 {signal.Signals(signum).name}，退出...")
        stop()

    signal.signal(signal.SIGTERM, signal_handler)  # taskkill
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C


def _reset_signal_handlers() -> None:
    """重置信号处理器为默认状态"""
    try:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass


def restart() -> None:
    """重启程序"""
    logger.debug("重启程序")

    app = QApplication.instance()
    if app:
        _reset_signal_handlers()
        app.quit()
        app.processEvents()

    os.execl(sys.executable, sys.executable, *sys.argv)


def stop(status: int = 0) -> NoReturn:
    """退出程序"""
    logger.info("退出程序...")
    app = QApplication.instance()
    if app:
        app.quit()
        app.processEvents()
    logger.info(f"程序退出({status})")
    sys.exit(status)


def crash() -> NoReturn:
    """崩溃程序"""
    raise Exception("Crash Test")
