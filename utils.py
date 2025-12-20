import atexit
import datetime as dt
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import psutil
import win32com.client
import win32con
import win32gui
from loguru import logger
from PySide6.QtCore import QtMsgType, qInstallMessageHandler

error_cooldown = dt.timedelta(seconds=2)  # 冷却时间(s)
ignore_errors = []
last_error_time = dt.datetime.now() - error_cooldown  # 上一次错误
error_dialog = None


class StreamToLogger:
    """重定向 print() 到 loguru"""

    def write(self, message):
        msg = message.strip()
        if msg:
            logger.opt(depth=1).info(msg)

    def flush(self):
        pass


def qt_message_handler(mode, context, message):  # noqa
    """Qt 消息转发到 loguru"""
    msg = message.strip()
    if not msg:
        return
    if mode == QtMsgType.QtCriticalMsg:
        logger.error(msg)
        logger.complete()
    elif mode == QtMsgType.QtFatalMsg:
        logger.critical(msg)
        logger.complete()
    else:
        logger.complete()


@logger.catch
def global_exceptHook(exc_type: type, exc_value: Exception, exc_tb: Any) -> None:
    # 增加安全模式判断？
    error_details = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    if error_details in ignore_errors:
        return
    global last_error_time, error_dialog
    current_time = dt.datetime.now()
    if current_time - last_error_time > error_cooldown:
        last_error_time = current_time
        # 获取异常抛出位置
        tb_last = exc_tb
        while tb_last.tb_next:  # 找到最后一帧
            tb_last = tb_last.tb_next
        frame = tb_last.tb_frame
        file_name = Path(frame.f_code.co_filename).name
        line_no = tb_last.tb_lineno
        func_name = frame.f_code.co_name
        process = psutil.Process()
        memory_info = process.memory_info()
        thread_count = process.num_threads()
        log_msg = f"""发生全局异常:
├─异常类型: {exc_type.__name__} {exc_type}
├─异常信息: {exc_value}
├─发生位置: {file_name}:{line_no} in {func_name}
├─运行状态: 内存使用 {memory_info.rss / 1024 / 1024:.1f}MB 线程数: {thread_count}
└─详细堆栈信息:"""
        tip_msg = f"""运行状态: 内存使用 {memory_info.rss / 1024 / 1024:.1f}MB 线程数: {thread_count}
└─异常类型: {exc_type.__name__} {exc_type}"""
        logger.opt(exception=(exc_type, exc_value, exc_tb), depth=0).error(log_msg)
        logger.complete()
        # if not error_dialog:
        #     w = ErrorDialog(f'{tip_msg}\n{error_details}')
        #     w.exec()


def init_exception_handler():
    logger.add(
        EA_EXECUTABLE.parent / "Logs" / "EasiAuto_{time}.log",
        rotation="1 MB",
        retention="1 minute",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )
    sys.stdout = StreamToLogger()
    sys.stderr = StreamToLogger()
    qInstallMessageHandler(qt_message_handler)
    atexit.register(logger.complete)

    sys.excepthook = global_exceptHook


def get_resource(file: str):
    """获取资源路径"""
    return str(EA_EXECUTABLE.parent / "resources" / file)


EA_EXECUTABLE = Path(sys.argv[0]).resolve().parent / "EasiAuto.exe"


def create_script(bat_content: str, file_name: str):
    """在桌面创建脚本"""
    shell = win32com.client.Dispatch("WScript.Shell")
    desktop_path = Path(shell.SpecialFolders("Desktop"))

    bat_path = desktop_path / file_name

    with bat_path.open("w", encoding="utf-8") as f:
        f.write(bat_content)


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
        logger.info(f"已找到标题包含 '{title}' 的窗口")
        return hwnds
    logger.warning(f"未找到标题包含 '{title}' 的窗口")


def get_window_by_pid(pid: int, target_title: str, strict: bool = True) -> int | None:
    """根据进程 PID 查找窗口句柄，支持部分标题匹配。"""
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
