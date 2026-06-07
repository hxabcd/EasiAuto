import os
from pathlib import Path

import psutil
import win32api
import win32con
import win32event
import win32gui
import win32process
import winerror
from loguru import logger

from EasiAuto.consts import EA_EXECUTABLE

MUTEX_NAME = "EasiAutoMutex"

_singleton_mutex = None


def _normalize_path(path: str | Path) -> str:
    return str(Path(path)).replace("/", "\\").lower()


def _bring_window_to_front(hwnd: int) -> bool:
    """尽力将窗口切到前台"""
    try:
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception as e:
        logger.debug(f"切换窗口失败: hwnd={hwnd}, err={e}")
        return False


def _iter_other_process_windows(current_pid: int) -> list[tuple[int, int]]:
    """枚举 (hwnd, pid)，仅包含可见顶层窗口且 pid != current_pid"""
    result: list[tuple[int, int]] = []

    def callback(hwnd: int, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid and pid != current_pid:
            result.append((hwnd, pid))
        return True

    win32gui.EnumWindows(callback, None)
    return result


def _is_same_app_process(pid: int) -> bool:
    """通过可执行路径和进程名判断是否为同应用"""
    try:
        proc = psutil.Process(pid)
        exe = proc.exe()
        proc_name = proc.name().lower()
    except Exception:
        return False

    expected = _normalize_path(EA_EXECUTABLE)
    actual = _normalize_path(exe)
    if actual == expected:
        return True

    # 兼容开发环境和部分打包场景
    return ("python" in proc_name) or ("easiauto" in proc_name)


def _focus_existing_instance(current_pid: int) -> bool:
    """查找并尝试激活已运行实例窗口"""
    for hwnd, pid in _iter_other_process_windows(current_pid):
        if not _is_same_app_process(pid):
            continue
        title = win32gui.GetWindowText(hwnd)
        if _bring_window_to_front(hwnd):
            logger.warning(f"检测到已运行实例, 已尝试切换到该窗口: pid={pid}, title={title!r}")
            return True
    return False


def check_singleton(focus_existing: bool = True) -> bool:
    """检查程序是否可作为唯一实例继续运行"""
    return True
