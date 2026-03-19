import subprocess
import time
import winreg
from abc import abstractmethod
from contextlib import suppress
from pathlib import Path

import win32gui
from loguru import logger

from PySide6.QtCore import QThread, Signal

from EasiAuto.common.config import config
from EasiAuto.common.utils import QABCMeta, get_scale, get_screen_size, switch_window


class LoginCancelled(Exception):
    pass

class BaseAutomator(QThread, metaclass=QABCMeta):
    failed = Signal(str)
    task_update = Signal(str)
    progress_update = Signal(str)

    def __init__(self, account: str, password: str) -> None:
        super().__init__()
        self.setObjectName(f"Automator:{self.__class__.__name__}")

        self.account = account
        self.password = password
        self.easinote_path: Path | None = self.get_easinote_path()
        self.easiauto_hwnd: int | None = None

        self.compatibility_mode: bool = False
        screen_size = get_screen_size()
        scale = get_scale()
        if config.Login.ForceEnableScaling:
            logger.warning("已强制启用兼容模式输入")
            self.compatibility_mode = True
        elif screen_size[1] / scale < 720:
            logger.info("检测到屏幕高度较低，启用兼容模式输入")
            self.compatibility_mode = True

    def input(self, text: str):
        import pyautogui
        import pyperclip

        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        if self.compatibility_mode:
            # 使用剪贴板输入，避免输入法遮挡等问题
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        else:
            pyautogui.typewrite(text, interval=0.01)

    def check(self):
        if self.isInterruptionRequested():
            raise LoginCancelled("收到中断请求")
        return True

    @property
    def safe_for_log_password(self) -> str:
        """将密码模糊处理以防止泄露"""
        return self.password[0] + "*" * (len(self.password) - 2) + self.password[-1]

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

    def kill_easinote_processes(self):
        logger.info("终止进程")
        self.progress_update.emit("终止希沃白板进程")

        cmd_list = [["taskkill", "/f", "/im", config.Login.EasiNote.ProcessName]]
        if config.Login.KillAgent:
            cmd_list.append(["taskkill", "/f", "/im", "EasiAgent.exe"])

        for command in cmd_list:
            logger.debug(f"命令：{' '.join(command)}")
            subprocess.run(command, shell=True, check=False)
        time.sleep(config.Login.Timeout.Terminate)  # 等待终止

    def start_easinote(self, path: Path, args: str):
        logger.info("启动程序")
        self.progress_update.emit("启动希沃白板")
        logger.debug(f"路径：{path}，参数：{args}")

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

    def wait_for_window(self, window_title: str, timeout: float, interval: float) -> int | None:
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
        while elapsed < timeout and self.check():
            self.progress_update.emit(f"等待{window_title}窗口打开 ({int(elapsed)}/{int(timeout)}s)")
            if config.Debug.AlternateFindWindowMethod:
                windows = self._enum_all_windows()
                for w in windows:
                    if window_title in w[1]:
                        hwnd = w[0]
                        break
            else:
                hwnd = win32gui.FindWindow(None, window_title)
            if config.Debug.VerboseLog:
                self._enum_all_windows()
            if hwnd:
                return hwnd
            time.sleep(interval)
            elapsed += interval
        return False

    def restart_easinote(self):
        """重启希沃进程"""

        logger.info("尝试重启希沃进程")
        self.task_update.emit("重启希沃进程")

        if self.easinote_path is None:
            logger.error("希沃白板目录不存在")
            raise LoginCancelled("希沃白板目录不存在")

        self.kill_easinote_processes()
        self.check()
        self.start_easinote(path=self.easinote_path, args=config.Login.EasiNote.Args)

        window_title = config.Login.EasiNote.WindowTitle
        timeout = config.Login.Timeout.LaunchPollingTimeout
        interval = config.Login.Timeout.LaunchPollingInterval

        logger.info(f"等待{window_title}窗口打开...")
        self.easinote_hwnd = self.wait_for_window(window_title, timeout, interval)
        if self.easinote_hwnd:
            logger.success(f"{window_title}窗口已打开")
            self.task_update.emit("等待登录")
            self.progress_update.emit("希沃白板已启动")
            time.sleep(config.Login.Timeout.AfterLaunch)
            with suppress(Exception):
                switch_window(self.easinote_hwnd, press_key=config.Debug.AlternateSwitchWindowMethod)
        else:
            logger.error(f"{window_title}窗口在{timeout}秒内未打开")
            raise TimeoutError(f"{window_title}窗口在{timeout}秒内未打开")

    @abstractmethod
    def login(self):
        """自动登录"""
        ...

    def run(self):
        """完整登录流程"""
        retries = 0
        while self.check():
            try:
                self.restart_easinote()
                self.login()

                return
            except LoginCancelled:
                return
            except Exception as e:
                retries += 1

                if retries <= config.App.MaxRetries:
                    logger.error(f"登录过程中发生错误 ({type(e).__name__}): {e}")
                    logger.warning(f"将在2s后重试（尝试 {retries}/{config.App.MaxRetries}）")
                    time.sleep(2)
                else:
                    logger.critical(f"{retries}次尝试均登录失败: {e}")
                    self.failed.emit(str(e))
                    return
