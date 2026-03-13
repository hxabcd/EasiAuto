import subprocess
import time
import winreg
from abc import abstractmethod
from pathlib import Path

import pyautogui
import pyperclip
import win32gui
from loguru import logger

from PySide6.QtCore import QThread, Signal

from EasiAuto.common.config import config
from EasiAuto.common.utils import QABCMeta, get_scale, get_screen_size, switch_window

compatibility_mode = False

screen_size = get_screen_size()
scale = get_scale()
logger.debug(f"当前分辨率: {screen_size[0]}x{screen_size[1]}，缩放比例: {scale}")
if config.Login.ForceEnableScaling:
    logger.warning("已强制启用兼容模式输入")
    compatibility_mode = True
elif screen_size[1] / scale < 720:
    logger.info("检测到屏幕高度较低，启用兼容模式输入")
    compatibility_mode = True


def safe_input(text: str):
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("backspace")
    if compatibility_mode:
        # 使用剪贴板输入，避免输入法遮挡等问题
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.typewrite(text, interval=0.01)



class BaseAutomator(QThread, metaclass=QABCMeta):
    finished = Signal(bool, str)
    task_update = Signal(str)
    progress_update = Signal(str)

    def __init__(self, account: str, password: str) -> None:
        super().__init__()
        self.account = account
        self.password = password
        self.easinote_path = self.get_easinote_path()

    @property
    def safe_for_log_password(self) -> str:
        """将密码模糊处理以防止泄露"""
        return self.password[0] + "*" * (len(self.password) - 2) + self.password[-1]

    @staticmethod
    def get_easinote_path() -> Path:
        if config.Login.EasiNote.AutoPath:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\WOW6432Node\Seewo\EasiNote5",
                ) as key:
                    path = winreg.QueryValueEx(key, "ExePath")[0]
                    logger.debug(f"自动获取到路径: {path}")
            except Exception:
                logger.warning("自动获取路径失败，使用默认路径")
                path = r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe"
        else:
            path = config.Login.EasiNote.Path
        return Path(path)

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

    def start_easinote(self):
        logger.info("启动程序")
        self.progress_update.emit("等待程序启动")
        logger.debug(f"路径：{self.easinote_path}，参数：{config.Login.EasiNote.Args}")

        args = config.Login.EasiNote.Args

        if not Path(self.easinote_path).exists():
            logger.error(f"希沃白板可执行文件不存在: {self.easinote_path}")
            raise FileNotFoundError(f"希沃白板可执行文件不存在: {self.easinote_path}")

        subprocess.Popen([self.easinote_path, *args.split(" ")] if args != "" else self.easinote_path)

    def wait_for_window(self, window_title: str, timeout: float, interval: float) -> bool:
        elapsed = 0
        while elapsed < timeout:
            self.hwnd = win32gui.FindWindow(None, window_title)
            if self.hwnd:
                return True
            time.sleep(interval)
            elapsed += interval
        return False

    def restart_easinote(self):
        """重启希沃进程"""

        logger.info("尝试重启希沃进程")
        self.task_update.emit("重启希沃进程")

        self.kill_easinote_processes()
        self.start_easinote()

        window_title = config.Login.EasiNote.WindowTitle
        timeout = config.Login.Timeout.LaunchPollingTimeout
        interval = config.Login.Timeout.LaunchPollingInterval

        logger.info(f"等待窗口 {window_title} 打开...")
        if self.wait_for_window(window_title, timeout, interval):
            logger.success(f"窗口已打开：{window_title}")
            self.task_update.emit("等待登录")
            self.progress_update.emit("希沃白板已启动")
            time.sleep(config.Login.Timeout.AfterLaunch)
            switch_window(self.hwnd)
        else:
            logger.error(f"窗口在 {timeout} 秒内未打开：{window_title}")
            raise TimeoutError(f"窗口在 {timeout} 秒内未打开：{window_title}")

    @abstractmethod
    def login(self):
        """自动登录"""
        ...

    def run(self):
        """完整登录流程"""
        retries = 0
        while True:
            try:
                self.restart_easinote()
                self.login()

                self.finished.emit(True, "登录完成")
                return
            except BaseException as e:
                retries += 1

                if retries <= config.App.MaxRetries:
                    logger.error(f"登录过程中发生错误 ({type(e).__name__}): {e}")
                    logger.warning(f"将在2s后重试（尝试 {retries}/{config.App.MaxRetries}）")
                    time.sleep(2)
                else:
                    logger.critical(f"{retries}次尝试均登录失败: {e}")
                    self.finished.emit(False, f"登录失败: {e}")
                    return
