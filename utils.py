import logging
import os
import sys
import time
from pathlib import Path

import win32con
import win32gui

from config import Config, get_log_level


def set_logger(level=logging.WARNING):
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
    # 若配置文件存在则加载，否则创建默认配置文件并退出
    if config_path.exists():
        return Config.load(str(config_path))
    else:
        logging.warning(f"配置文件 {config_path} 不存在，自动创建")
        config = Config.load(str(config_path))
        config.save()
        time.sleep(3)
        sys.exit(0)


def init():
    """初始化"""
    set_logger()  # 预初始化

    config = load_config()

    try:
        set_logger(get_log_level[config.app.log_level])
        logging.info(f"当前日志级别：{config.app.log_level}")
    except ValueError:
        set_logger()
        logging.error(f"无效的日志级别：{config.app.log_level}，使用默认级别 WARNING")

    logging.info("初始化完成")

    # logging.debug(
    #     "载入的配置：\n%s" % "\n".join([f" - {key}: {value}" for key, value in config])
    # )
    # TODO: 嵌套格式无法正常打印

    return config


def switch_window_by_title(title):
    """通过窗口标题切换焦点"""

    def callback(hwnd, extra):
        if title in win32gui.GetWindowText(hwnd):
            extra.append(hwnd)

    hwnds = []
    # 枚举所有顶层窗口
    win32gui.EnumWindows(callback, hwnds)

    if hwnds:
        # 切换到找到的第一个窗口
        win32gui.ShowWindow(hwnds[0], win32con.SW_RESTORE)  # 确保窗口不是最小化状态
        win32gui.SetForegroundWindow(hwnds[0])  # 设置为前台窗口（获取焦点）
        logging.info(f"已切换到标题包含 '{title}' 的窗口")
    else:
        logging.warning(f"未找到标题包含 '{title}' 的窗口")
