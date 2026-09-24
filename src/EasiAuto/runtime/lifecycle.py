"""应用生命周期：退出、重启与退出信号处理。"""

from __future__ import annotations

import os
import signal
import sys
from typing import NoReturn

from loguru import logger

from PySide6.QtWidgets import QApplication


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
