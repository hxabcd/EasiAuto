import subprocess
import time
from abc import abstractmethod
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import SupportsIndex, SupportsInt

import win32gui
from loguru import logger

from PySide6.QtCore import QThread, Signal

from EasiAuto.core.exception_handler import capture_handled_exception
from EasiAuto.core.utils import (
    Point,
    QABCMeta,
    desensitize_account,
    get_scale,
    get_screen_size_physical,
    kill_process,
    switch_window,
)
from EasiAuto.integrations.easinote import api as easinote_api
from EasiAuto.integrations.easinote.env import resolve_is_iwb
from EasiAuto.integrations.easinote.patcher import fetch_current_login_info, is_patched
from EasiAuto.integrations.easinote.path import resolve_easinote_path
from EasiAuto.models.config import config
from EasiAuto.models.profile import profile


class LoginCancelled(Exception):  # noqa: N818
    """登录被手动取消"""


class LoginError(Exception):
    """登录异常"""

    def __init__(self, message: str, retry: bool = True) -> None:
        """
        Args:
            message (str): 异常信息
            retry (bool, optional): 是否允许错误重试
        """
        super().__init__(message)
        self.retry = retry


class LoginStatus(Enum):
    """登录流程的最终状态"""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BaseAutomator(QThread, metaclass=QABCMeta):
    succeeded = Signal()
    interrupted = Signal()
    failed = Signal(str)
    task_updated = Signal(str)
    progress_updated = Signal(str)
    # NOTE: 无法在子线程创建 UI，需要将信号传回主线程
    privacy_mask_show = Signal(int, int, int, int)  # x, y, width, height
    privacy_mask_hide = Signal()

    def __init__(self, account: str, password: str) -> None:
        super().__init__()
        self.setObjectName(f"Automator:{self.__class__.__name__}")

        self.account: str = account
        self.password: str = password
        self.easinote_path: Path | None = None
        self.easinote: subprocess.Popen | None = None
        self.easinote_args: str = ""
        self.easinote_hwnd: int = 0  # 由 prepare() 在等待窗口出现后写入
        self.is_iwb: bool = False  # 由 restart_easinote() 按机器环境检测

        self._prev_task: str | None = None
        self._prev_progress: str | None = None
        self._privacy_mask_shown: bool = False

    def check_interruption(self) -> None:
        """中断检查点"""
        if self.isInterruptionRequested():
            raise LoginCancelled("收到中断请求")

    def update_task(self, text: str):
        if text == self._prev_task:
            return
        self._prev_task = text

        logger.info(f"[任务] {text}")

        self.task_updated.emit(text)

    def update_progress(self, text: str):
        if text == self._prev_progress:
            return
        self._prev_progress = text

        logger.info(f"[进度] {text}")

        self.progress_updated.emit(text)

    @staticmethod
    def get_easinote_path() -> Path | None:

        path, source = resolve_easinote_path()
        if source == "registry":
            logger.debug(f"自动获取到路径: {path}")
        elif source == "fallback":
            logger.warning("自动获取路径失败, 使用默认路径")
        else:
            logger.debug(f"使用设置的路径: {config.Login.EasiNote.Path}")
        return path

    def kill_processes(self):
        target_list: list[str] = [config.Login.EasiNote.ProcessName]
        if config.Login.KillAgent:
            target_list.append("EasiAgent")
        if extra := config.Login.EasiNote.ExtraKills:
            target_list += extra.split(",")
        logger.debug(f"要终止的目标进程: {', '.join(target_list)}")

        for target in target_list:
            kill_process(
                target.strip().removesuffix(".exe"),
                force=True,
                wait=True,
                timeout=config.Login.Timeout.Terminate,
            )

    def start_easinote(self, path: Path, args: str) -> subprocess.Popen:
        """启动希沃白板

        Args:
            path (Path): 启动器可执行文件路径
            args (str): 启动参数，按空白字符分隔

        Returns:
            subprocess.Popen: 已启动的进程句柄

        Raises:
            LoginError: 启动失败（文件缺失、权限不足等）
        """
        logger.debug(f"路径: {path}, 参数: {args}")
        try:
            return subprocess.Popen([str(path.resolve()), *args.split()])
        except OSError as e:
            raise LoginError(f"启动希沃白板失败: {e}") from e

    def _enum_all_windows(self) -> list[tuple[int, str, str]]:
        """枚举所有顶层窗口"""

        def callback(hwnd, windows):
            window_text = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd) or ""
            if window_text or "easinote" in class_name.lower():
                windows.append((hwnd, window_text, class_name))
            return True

        windows = []
        win32gui.EnumWindows(callback, windows)

        return windows

    def _log_all_windows(self):
        windows = self._enum_all_windows()

        windows.sort(key=lambda x: x[1])

        logger.debug("==========当前窗口==========")
        for hwnd, text, class_name in windows:
            logger.debug(f"句柄: {hwnd:8x} | 标题: {text[:30]:30} | 类名: {class_name}")

    def _find_window(self, title: str) -> int:
        """按标题查找窗口句柄，未找到返回 0"""
        if config.Debug.AlternateFindWindowMethod:
            for hwnd, text, _ in self._enum_all_windows():
                if title in text:
                    return hwnd
            return 0
        return win32gui.FindWindow(None, title) or 0

    def wait_for_window(self, title: str, timeout: float, interval: float) -> int:
        """等待窗口出现

        Args:
            title (str): 目标窗口标题
            timeout (float): 超时时长
            interval (float): 检查间隔

        Returns:
            int: 窗口句柄

        Raises:
            LoginError: 超时仍未出现该窗口
            LoginCancelled: 等待期间收到中断请求
        """
        elapsed = 0.0
        while elapsed < timeout:
            self.check_interruption()

            self.update_progress(f"等待{title}窗口出现 ({int(elapsed)}/{int(timeout)}s)")
            if config.Debug.VerboseLog:
                self._log_all_windows()
            if hwnd := self._find_window(title):
                return hwnd
            time.sleep(interval)
            elapsed += interval

        raise LoginError(f"{title}窗口在{timeout}秒内未打开")

    def _after_easinote_dead(self):
        """希沃进程已终止、尚未重新启动时的扩展点"""

    def resolve_launch_args(self) -> str:
        """本次启动希沃白板实际使用的参数（子类可覆写以强制启动模式）"""
        return config.Login.EasiNote.Args

    def restart_easinote(self):
        """终止并按本次启动参数重启希沃白板

        Raises:
            LoginError: 启动器路径缺失或启动失败
        """
        path = self.easinote_path
        if path is None or not path.exists():
            # NOTE: 校验放在终止进程之前，避免启动器缺失时白白关掉用户的希沃白板
            raise LoginError("希沃白板可执行文件不存在", retry=False)

        logger.info("终止希沃进程")
        self.kill_processes()
        self.check_interruption()

        self._after_easinote_dead()

        # 按实际启动参数判定界面环境（命令行 -m 优先，否则探测本机硬件）
        args = self.resolve_launch_args()
        self.is_iwb = resolve_is_iwb(args)
        self.easinote_args = args

        logger.info("启动希沃白板")
        self.easinote = self.start_easinote(path=path, args=args)
        self.check_interruption()

    def _current_uid(self) -> str | None:
        """读取当前登录希沃账号的 userId；未修补或无登录信息时返回 None。"""
        info = fetch_current_login_info(False)
        if not info or info.get("statusCode") != 202:
            return None
        return info.get("userId") or None

    def check_logged_in(self) -> bool:
        """目标账号是否已登录（优先本地比对缓存，无缓存则联网解析目标 uid）"""
        if not is_patched():
            return False

        current_uid = self._current_uid()
        if not current_uid:
            return False

        target_uid = profile.get_login_uid(self.account)
        if not target_uid:
            try:
                result = easinote_api.login(self.account, self.password)
            except Exception:
                return False
            target_uid = result.user.uid
            if not target_uid:
                return False
            profile.set_login_uid(self.account, target_uid)

        return current_uid == target_uid

    def before_prepare(self):
        """prepare() 之前的扩展点，子类可覆写以插入额外的准备工作

        Raises:
            LoginError: 准备失败
            LoginCancelled: 应中止本次登录
        """

    def prepare(self):
        """准备登录

        Raises:
            LoginError: 路径缺失或其他准备失败
            LoginCancelled: 目标账号已登录
        """
        self.before_prepare()

        self.update_progress("获取希沃白板目录")
        self.easinote_path = self.get_easinote_path()
        if self.easinote_path is None:
            raise LoginError("希沃白板目录不存在", retry=False)

        if config.Login.SkipIfLoggedIn:
            self.update_progress("检查登录状态")
            if self.check_logged_in():
                raise LoginCancelled("该账号已登录")

        self.update_progress("重启希沃进程")
        self.restart_easinote()

        # 等待启动并唤起
        window_title = config.Login.EasiNote.WindowTitle

        self.easinote_hwnd = self.wait_for_window(
            window_title,
            config.Login.Timeout.LaunchPollingTimeout,
            config.Login.Timeout.LaunchPollingInterval,
        )
        self.update_task("等待登录")
        self.update_progress("希沃白板已启动")
        time.sleep(config.Login.Timeout.AfterLaunch)
        try:
            if not switch_window(self.easinote_hwnd, press_key=True):
                # 焦点未抢到时会继续执行，但后续模拟输入可能落到其他窗口
                logger.warning("未能将希沃白板窗口切到前台, 模拟输入可能落入其他窗口")
        except Exception as e:
            logger.warning(f"切换希沃白板窗口焦点时出错: {e}")

    @abstractmethod
    def login(self):
        """自动登录"""
        ...

    def show_privacy_mask(self, x: int, y: int, w: int, h: int) -> None:
        """显示隐私保护遮罩；关闭的实验性选项下不显示"""
        if not config.Experimental.PrivacyMask.Enabled:
            return

        self._privacy_mask_shown = True
        self.privacy_mask_show.emit(x, y, w, h)

    def hide_privacy_mask(self) -> None:
        """隐藏隐私保护遮罩，重复调用无效"""
        if not self._privacy_mask_shown:
            return

        self._privacy_mask_shown = False
        self.privacy_mask_hide.emit()

    def on_login_finished(self, status: LoginStatus, error: str | None) -> None:
        """登录流程结束后的收尾（无论成功、失败或取消都会调用一次）

        Args:
            status (LoginStatus): 最终状态
            error (str | None): 失败原因，成功或取消时为 None
        """

    def _finalize(self, status: LoginStatus, error: str | None = None) -> None:
        """统一收尾并发出结果信号：保证遮罩清理与子类回调在任何情况下都执行"""
        self.hide_privacy_mask()
        try:
            self.on_login_finished(status, error)
        except Exception as e:
            logger.error(f"登录收尾回调执行失败: {type(e).__name__}: {e}")

        match status:
            case LoginStatus.SUCCESS:
                config.Statistics.LoginSuccessCounts += 1
                self.succeeded.emit()
            case LoginStatus.CANCELLED:
                config.Statistics.LoginInterruptCounts += 1
                self.interrupted.emit()
            case LoginStatus.FAILED:
                self.failed.emit(error or "未知错误")

    def _record_attempt(self) -> None:
        """统计本次登录尝试"""
        config.Statistics.LoginCounts += 1
        account_hash = desensitize_account(self.account)
        config.Statistics.LoginCountsPerAccount[account_hash] = (
            config.Statistics.LoginCountsPerAccount.get(account_hash, 0) + 1
        )

    def run(self):
        """完整登录流程"""
        time_start = time.monotonic()
        self._record_attempt()

        max_retries = config.App.MaxRetries
        retries = 0
        status = LoginStatus.FAILED
        error: str | None = None

        while True:
            try:
                self.check_interruption()

                self.update_task("正在准备登录")
                self.prepare()

                self.update_task("正在自动登录")
                self.login()

                self.update_task("完成")
                self.update_progress("登录完成")
                status = LoginStatus.SUCCESS
                break
            except LoginCancelled as e:
                logger.info(f"登录被取消: {e}")
                status = LoginStatus.CANCELLED
                break
            except Exception as e:
                error = str(e)

                if not getattr(e, "retry", True):
                    logger.error(f"登录失败 (重试已禁用)\n{type(e).__name__}: {e}")
                    break

                if retries < max_retries:
                    retries += 1
                    self.hide_privacy_mask()  # 重试会重新走 prepare()，避免遮罩残留在屏幕上
                    logger.error(f"登录失败\n{type(e).__name__}: {e}")
                    logger.warning(f"将在2s后重试 (重试 {retries}/{max_retries}) ")
                    time.sleep(2)
                    continue

                logger.critical(f"多次尝试均登录失败\n{type(e).__name__}: {e}")
                capture_handled_exception(
                    e,
                    source="automator",
                    extra_context={
                        "retries": f"{retries}/{max_retries}",
                        "automator": self.__class__.__name__,
                        "current_task": self._prev_task,
                        "current_progress": self._prev_progress,
                    },
                )
                break

        self._finalize(status, error)

        elapsed = time.monotonic() - time_start
        logger.info(f"登录流程耗时: {elapsed:.2f}秒")
        config.Statistics.TotalLoginTime += elapsed
        config.Statistics.MaxLoginTime = max(config.Statistics.MaxLoginTime, elapsed)


class PyAutoGuiBaseAutomator(BaseAutomator):
    def __init__(self, account: str, password: str) -> None:
        super().__init__(account, password)

        self.compatibility_mode: bool = False
        screen_size = get_screen_size_physical()
        scale = get_scale()
        if config.Login.ForceCompatibilityMode:
            logger.warning("已强制启用兼容模式输入")
            self.compatibility_mode = True
        elif screen_size[1] / scale < 720:
            logger.info("检测到屏幕高度较低, 启用兼容模式输入")
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
