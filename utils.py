import logging
import os
import sys
from pathlib import Path

import win32con
import win32gui

from config import Config, get_log_level


def set_logger(level=logging.WARNING):
    try:  # 使用彩色日志
        import coloredlogs

        coloredlogs.install(
            level=level,
            fmt="[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    except Exception:  # 回退基本日志
        logging.basicConfig(
            level=level,
            format="[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
            force=True,
        )


def get_resource(file: str):
    """获取资源路径"""
    if hasattr(sys, "frozen"):
        base_path = getattr(sys, "_MEIPASS")
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "resources", file)


def get_executable_dir():
    return Path(sys.argv[0]).resolve().parent


def load_config(config_file="config.json") -> Config:
    """加载配置文件"""
    config_path = get_executable_dir() / config_file

    logging.debug(f"查找配置文件: {config_path}")

    return Config.load(str(config_path))


def init():
    """初始化"""

    set_logger()  # 预初始化

    config = load_config()

    try:
        set_logger(get_log_level[config.App.LogLevel])
        logging.info(f"当前日志级别：{config.App.LogLevel}")
    except ValueError:
        set_logger()
        logging.error(f"无效的日志级别：{config.App.LogLevel}，使用默认级别 WARNING")
    logging.info("初始化完成")

    # logging.debug(
    #     "载入的配置：\n%s" % "\n".join([f" - {key}: {value}" for key, value in config])
    # )
    # TODO: 嵌套格式无法正常打印

    return config


def toggle_skip(config: Config, status: bool, file="config.json"):
    config.Login.SkipOnce = status
    path = get_executable_dir() / file
    with path.open("w", encoding="utf-8") as f:
        data = config.model_dump_json(indent=4)
        f.write(data)


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
        logging.info(f"已找到标题包含 '{title}' 的窗口")
        return hwnds
    else:
        logging.warning(f"未找到标题包含 '{title}' 的窗口")


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
