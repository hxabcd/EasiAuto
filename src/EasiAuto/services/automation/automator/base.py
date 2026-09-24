"""自动登录基类

编排一次登录流程：准备（终止并重启希沃白板）→ 执行子类的登录动作 → 统一收尾与结果上报。
具体的点击/输入手段由子类实现。
"""

from __future__ import annotations

import subprocess
import time
from abc import abstractmethod
from pathlib import Path

from loguru import logger

from PySide6.QtCore import QThread, Signal

from EasiAuto.core import window
from EasiAuto.core.qt_abc import QABCMeta
from EasiAuto.integrations.easinote import api as easinote_api
from EasiAuto.integrations.easinote import pipe
from EasiAuto.integrations.easinote import process as easinote_process
from EasiAuto.integrations.easinote.env import resolve_is_iwb
from EasiAuto.integrations.easinote.patcher import is_patched
from EasiAuto.integrations.easinote.path import resolve_easinote_path
from EasiAuto.models.config import config
from EasiAuto.models.profile import profile
from EasiAuto.runtime.exception_handler import capture_handled_exception

from .errors import LoginCancelled, LoginError, LoginStatus


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
                window.log_windows()
            if hwnd := window.find_window(title, substring=config.Debug.AlternateFindWindowMethod):
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
        easinote_process.kill_targets(
            config.Login.EasiNote.ProcessName,
            kill_agent=config.Login.KillAgent,
            extra_kills=config.Login.EasiNote.ExtraKills,
            timeout=config.Login.Timeout.Terminate,
        )
        self.check_interruption()

        self._after_easinote_dead()

        # 按实际启动参数判定界面环境（命令行 -m 优先，否则探测本机硬件）
        args = self.resolve_launch_args()
        self.is_iwb = resolve_is_iwb(args)
        self.easinote_args = args

        logger.info("启动希沃白板")
        try:
            self.easinote = easinote_process.launch(path, args)
        except OSError as e:
            raise LoginError(f"启动希沃白板失败: {e}") from e
        self.check_interruption()

    def _current_uid(self) -> str | None:
        """读取当前登录希沃账号的 userId；未修补或无登录信息时返回 None。"""
        info = pipe.read_current_login_info()
        if info is None or not info.is_logged_in:
            return None
        return info.user_id or None

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
            if not window.switch_window(self.easinote_hwnd, press_key=True):
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
                self.succeeded.emit()
            case LoginStatus.CANCELLED:
                self.interrupted.emit()
            case LoginStatus.FAILED:
                self.failed.emit(error or "未知错误")

    def run(self):
        """完整登录流程"""
        time_start = time.monotonic()
        config.Statistics.record_start(self.account)

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
        config.Statistics.record_result(status.value, elapsed)
