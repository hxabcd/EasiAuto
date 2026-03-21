import subprocess
import time
import winreg
from abc import abstractmethod
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import SupportsIndex, SupportsInt

import win32gui
from loguru import logger

from PySide6.QtCore import QThread, Signal

from EasiAuto.common.config import config
from EasiAuto.common.utils import Point, QABCMeta, get_scale, get_screen_size, kill_process, switch_window


class LoginCancelled(Exception):
    pass


class LoginError(Exception):
    pass


class BaseAutomator(QThread, metaclass=QABCMeta):
    failed = Signal(str)
    task_update = Signal(str)
    progress_update = Signal(str)

    def __init__(self, account: str, password: str) -> None:
        super().__init__()
        self.setObjectName(f"Automator:{self.__class__.__name__}")

        self.account: str = account
        self.password: str = password
        self.easinote_path: Path | None = self.get_easinote_path()
        self.easiauto_hwnd: int | None = None

        self._prev_task: str | None = None
        self._prev_progress: str | None = None

    def check_interruption(self) -> None:
        """中断检查点"""
        if self.isInterruptionRequested():
            raise LoginCancelled("收到中断请求")

    def update_task(self, text: str):
        if text == self._prev_task:
            return
        self._prev_task = text

        logger.info(f"[任务] {text}")

        self.task_update.emit(text)

    def update_progress(self, text: str):
        if text == self._prev_progress:
            return
        self._prev_progress = text

        logger.info(f"[进度] {text}")

        self.progress_update.emit(text)

    @staticmethod
    def get_easinote_path() -> Path | None:
        if config.Login.EasiNote.AutoPath:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\WOW6432Node\Seewo\EasiNote5",
                ) as key:
                    path_str = winreg.QueryValueEx(key, "ExePath")[0]
                    logger.debug(f"自动获取到路径: {path_str}")
            except Exception:
                path_str = r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe"
                logger.warning("自动获取路径失败，使用默认路径")
        else:
            path_str = config.Login.EasiNote.Path
            logger.debug(f"使用设置的路径: {path_str}")

        path = Path(path_str).resolve()
        return path if path.exists() else None

    def kill_seewo_processes(self):
        target_list = [config.Login.EasiNote.ProcessName]
        if config.Login.KillAgent:
            target_list.append("EasiAgent")
        if extra := config.Login.EasiNote.ExtraKills:
            target_list += extra.split(",")
        logger.debug(f"要终止的目标进程：{target_list}")

        for target in target_list:
            kill_process(
                target.strip().removesuffix(".exe"),
                force=True,
                wait=True,
                timeout=config.Login.Timeout.Terminate,
            )

    def start_easinote(self, path: Path, args: str):
        logger.debug(f"启动参数: {path=}, {args=}")
        subprocess.Popen([path] + args.split(" "))

    def _enum_all_windows(self) -> list[tuple[int, str, str]]:
        """枚举所有顶层窗口"""

        def callback(hwnd, windows):
            # if win32gui.IsWindowVisible(hwnd):  # 只获取可见窗口
            window_text = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            if window_text or "easinote" in class_name.lower():
                windows.append((hwnd, window_text, class_name))
            return True

        windows = []
        win32gui.EnumWindows(callback, windows)

        return windows

    def _log_all_windows(self):
        windows = self._enum_all_windows()

        # 按窗口标题排序
        windows.sort(key=lambda x: x[1])

        logger.debug("==========当前窗口==========")
        for hwnd, text, class_name in windows:
            logger.debug(f"句柄: {hwnd:8x} | 标题: {text[:30]:30} | 类名: {class_name}")

    def wait_for_window(self, title: str, timeout: float, interval: float) -> int | None:
        """等待窗口出现

        Args:
            window_title (str): 目标窗口标题
            timeout (float): 超时时长
            interval (float): 检查间隔

        Returns:
            int: 窗口句柄
        """
        elapsed = 0
        hwnd = None
        while elapsed < timeout:
            self.check_interruption()

            self.update_progress(f"等待{title}窗口打开 ({int(elapsed)}/{int(timeout)}s)")
            if config.Debug.AlternateFindWindowMethod:
                windows = self._enum_all_windows()
                for w in windows:
                    if title in w[1]:
                        hwnd = w[0]
                        break
            else:
                hwnd = win32gui.FindWindow(None, title)
            if config.Debug.VerboseLog:
                self._enum_all_windows()
            if hwnd:
                return hwnd
            time.sleep(interval)
            elapsed += interval
        return False

    def restart_easinote(self):
        """重启希沃进程"""

        if self.easinote_path is None:
            raise LoginCancelled("希沃白板目录不存在")

        self.update_progress("终止希沃进程")
        self.kill_seewo_processes()
        self.check_interruption()

        self.update_progress("启动希沃白板")
        self.start_easinote(path=self.easinote_path, args=config.Login.EasiNote.Args)
        self.check_interruption()

        window_title = config.Login.EasiNote.WindowTitle
        timeout = config.Login.Timeout.LaunchPollingTimeout
        interval = config.Login.Timeout.LaunchPollingInterval

        self.easinote_hwnd = self.wait_for_window(window_title, timeout, interval)
        if self.easinote_hwnd:
            self.update_task("等待登录")
            self.update_progress("希沃白板已启动")
            time.sleep(config.Login.Timeout.AfterLaunch)
            with suppress(Exception):
                switch_window(self.easinote_hwnd)
        else:
            raise TimeoutError(f"{window_title}窗口在{timeout}秒内未打开")

    @abstractmethod
    def login(self):
        """自动登录"""
        ...

    def run(self):
        """完整登录流程"""
        retries = 0
        while True:
            try:
                self.check_interruption()

                self.update_progress("开始登录")
                self.update_task("重启希沃进程")
                self.restart_easinote()

                self.update_task("正在自动登录")
                self.login()

                self.update_progress("登录完成")
                self.update_task("完成")

                return
            except LoginCancelled:
                return
            except Exception as e:
                retries += 1

                if retries <= config.App.MaxRetries:
                    logger.error(f"登录过程中发生错误\n{type(e).__name__}: {e}")
                    logger.warning(f"将在2s后重试（尝试 {retries}/{config.App.MaxRetries}）")
                    time.sleep(2)
                else:
                    logger.critical(f"{retries}次尝试均登录失败\n{type(e).__name__}: {e}")
                    self.failed.emit(str(e))
                    return

class PyAutoGuiBaseAutomator(BaseAutomator):
    def __init__(self, account: str, password: str) -> None:
        super().__init__(account, password)

        self.compatibility_mode: bool = False
        screen_size = get_screen_size()
        scale = get_scale()
        if config.Login.ForceEnableScaling:
            logger.warning("已强制启用兼容模式输入")
            self.compatibility_mode = True
        elif screen_size[1] / scale < 720:
            logger.info("检测到屏幕高度较低，启用兼容模式输入")
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
