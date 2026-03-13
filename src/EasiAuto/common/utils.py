import ctypes
import os
import signal
import sys
from pathlib import Path
from typing import NoReturn

import win32com.client
import win32con
import win32gui
from loguru import logger

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

from EasiAuto.common.consts import EA_BASEDIR, EA_EXECUTABLE


def get_resource(filename: str):
    """获取资源路径"""
    return str(EA_EXECUTABLE.parent / "resources" / filename)


# 防止单例冲突，不使用 Qt 获取屏幕数据
def get_scale() -> float:
    """获取当前系统缩放比例"""
    ctypes.windll.shcore.SetProcessDpiAwareness(1)

    hdc = ctypes.windll.user32.GetDC(0)
    dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
    ctypes.windll.user32.ReleaseDC(0, hdc)

    return dpi / 96.0


def get_screen_size() -> tuple[int, int]:
    """获取屏幕尺寸

    Returns:
        tuple[int, int]: 屏幕宽度, 屏幕长度
    """
    ctypes.windll.user32.SetProcessDPIAware()

    width = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
    height = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN

    return width, height


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
        shortcut.IconLocation = get_resource("EasiAutoShortcut.ico")
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


def switch_window(hwnd: int):
    """通过句柄切换焦点"""
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)  # 确保窗口不是最小化状态
    win32gui.SetForegroundWindow(hwnd)  # 设置为前台窗口（获取焦点）


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
        _, window_pid = win32gui.GetWindowThreadProcessId(hwnd)
        if window_pid == pid:
            window_title = win32gui.GetWindowText(hwnd)
            if (target_title == window_title) if strict else (target_title in window_title):
                hwnd_found = hwnd
                return False  # 找到就停止枚举
        return True

    win32gui.EnumWindows(callback, None)
    return hwnd_found


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
        stop(0)

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


def clean_up(status):
    app = QApplication.instance()
    logger.debug(f"程序退出({status})")
    if not app:
        os._exit(status)


def stop(status: int = 0) -> None:
    """退出程序"""
    logger.debug("退出程序...")
    app = QApplication.instance()
    if app:
        app.quit()
        app.processEvents()
    clean_up(status)


def crash() -> NoReturn:
    """崩溃程序"""
    raise Exception("Crash Test")
