"""管理员提权工具 — 按需通过 UAC 以管理员权限执行自身。

仅在执行「修补希沃白板」等需要写入系统目录的操作时使用，避免整个应用常驻管理员权限。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from subprocess import CREATE_NO_WINDOW  # noqa: F401  (仅用于类型/常量参考)

from loguru import logger

from EasiAuto.consts import EA_EXECUTABLE, IS_DEV

# ShellExecuteEx 错误码：用户在 UAC 弹窗中选择了「否」
ERROR_CANCELLED = 1223

# SEE_MASK_NOCLOSEPROCESS：执行后返回进程句柄以便等待
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NO_CONSOLE = 0x00008000

INFINITE = 0xFFFFFFFF
WAIT_FAILED = 0xFFFFFFFF
STILL_ACTIVE = 259


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def is_admin() -> bool:
    """检测当前进程是否已具备管理员权限。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as e:
        logger.warning(f"检测管理员权限失败，按非管理员处理: {e}")
        return False


def run_elevated_wait(params: str) -> tuple[bool, int]:
    """以管理员权限启动 EA_EXECUTABLE 并阻塞等待其退出。

    通过 UAC 弹窗请求提权重启自身（仅该子进程提权，不影响当前进程）。

    Args:
        params: 传递给子进程的命令行参数字符串（如 ``"patch --on"``）

    Returns:
        (launched, exit_code)
        - launched=True 且 exit_code==0 表示子进程成功完成
        - launched=True 且 exit_code!=0 表示子进程启动但操作失败
        - launched=False 表示 UAC 被拒绝或启动失败（exit_code 为 -1）
    """
    # 开发环境无打包 exe，无法以 runas 启动自身，调用方应回退到原地执行
    if IS_DEV or not EA_EXECUTABLE.exists():
        logger.warning("开发环境或可执行文件不存在，跳过提权")
        return (False, -1)

    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(_SHELLEXECUTEINFOW)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    info.hwnd = None
    info.lpVerb = "runas"
    info.lpFile = str(EA_EXECUTABLE)
    info.lpParameters = params
    info.lpDirectory = str(EA_EXECUTABLE.parent)
    info.nShow = 0  # SW_HIDE：提权工作进程不显示窗口
    info.hProcess = None

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.get_last_error()
        # ERROR_CANCELLED 表示用户在 UAC 弹窗中拒绝授权
        if err == ERROR_CANCELLED:
            logger.info("用户拒绝了 UAC 授权")
        else:
            logger.error(f"ShellExecuteExW 失败，错误码: {err}")
        return (False, -1)

    handle = info.hProcess
    if not handle:
        logger.error("未获取到子进程句柄")
        return (False, -1)

    try:
        # 阻塞等待子进程退出。修补可能耗时数十秒（DllPatcher），不设超时。
        if kernel32.WaitForSingleObject(handle, INFINITE) == WAIT_FAILED:
            err = ctypes.get_last_error()
            logger.error(f"等待子进程失败，错误码: {err}")
            return (False, -1)

        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            err = ctypes.get_last_error()
            logger.error(f"获取退出码失败，错误码: {err}")
            return (False, -1)

        code = int(exit_code.value)
        logger.debug(f"提权子进程退出码: {code}")
        return (True, code)
    finally:
        kernel32.CloseHandle(handle)
