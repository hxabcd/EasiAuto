"""应用入口：单实例协调、命令行分发与登录流程的生命周期管理"""

import atexit
import sys
from argparse import Namespace
from contextlib import contextmanager, suppress
from datetime import UTC, datetime

from loguru import logger
from packaging.version import Version

from PySide6.QtCore import QLocale, Qt, QThread, QTimer

from EasiAuto import __version__, cli
from EasiAuto.consts import IPC_SERVER_NAME, SINGLETON_MUTEX_NAME
from EasiAuto.models.config import UpdateMode, config
from EasiAuto.models.profile import BaseAutomation
from EasiAuto.runtime import compatibility_patches
from EasiAuto.runtime.exception_handler import init_exception_handler
from EasiAuto.runtime.ipc import ArgvIpcServer, acquire_single_instance_mutex, send_argv_to_primary
from EasiAuto.runtime.lifecycle import init_exit_signal_handlers, stop
from EasiAuto.services import announcement_service, update_service
from EasiAuto.services.automation import automation_manager
from EasiAuto.services.update_service import UpdateError, cleanup_update_cache
from EasiAuto.view.helpers import cleanup_widget
from EasiAuto.view.login_preflight import LoginPreflight
from EasiAuto.view.main_window import MainWindow
from EasiAuto.view.notifications import ToastNotifier
from EasiAuto.view.shortcuts import migrate_desktop_shortcut_icon
from EasiAuto.view.tokens import BRAND

init_exception_handler()
init_exit_signal_handlers()


def shutdown():
    for action in (
        announcement_service.shutdown,
        update_service.shutdown,
        lambda: setattr(
            config.Statistics,
            "TotalRunTime",
            config.Statistics.TotalRunTime
            + (datetime.now(UTC) - config.Statistics.ThisInstanceLaunchTime).total_seconds(),
        ),
    ):
        with suppress(Exception):
            action()


atexit.register(shutdown)


class PostLoginUpdateThread(QThread):
    def run(self) -> None:
        try:
            decision = update_service.check()
            if decision.available and decision.downloads:
                if config.Update.Mode >= UpdateMode.CHECK_AND_INSTALL:
                    file = update_service.download_update(decision.downloads[0], allow_latency_check=True)
                    update_service.apply_script(file, reopen=False)
                else:
                    ToastNotifier().show("更新可用", f"新版本：{decision.target_version}")
        except UpdateError as e:
            logger.warning(f"检查更新时发生异常, 已跳过: {e}")
        except Exception as e:
            logger.error(f"检查更新时发生未预期异常, 已跳过: {e}")


class Launcher:
    def __init__(self) -> None:
        self.main_window: MainWindow | None = None
        self.preflight = LoginPreflight()

        self._singleton_mutex: int | None = None

        self.login_running: bool = False
        self.stop_requested: bool = False

        self.ipc_server: ArgvIpcServer | None = None
        self._ipc_context: bool = False
        self._current_login_triggered_via_ipc: bool = False
        self._post_login_update_thread: PostLoginUpdateThread | None = None

        automation_manager.finished.connect(self._on_login_finished)
        automation_manager.failed.connect(self._on_login_failed)
        automation_manager.privacy_mask_show.connect(self.preflight.show_privacy_mask)
        automation_manager.privacy_mask_hide.connect(self.preflight.hide_privacy_mask)

    @property
    def ipc_context(self) -> bool:
        """当前是否处于「由次实例转发触发」的上下文"""
        return self._ipc_context

    def is_unique_instance(self) -> bool:
        """检查程序是否可作为唯一实例继续运行"""
        self._singleton_mutex = acquire_single_instance_mutex(SINGLETON_MUTEX_NAME)
        return self._singleton_mutex is not None

    def show_settings_window(self, navigate_to: str | None = None) -> None:
        if self.main_window is None:
            self.main_window = MainWindow()
            self.main_window.runAutomation.connect(self._handle_login_request_from_ui)
        self.main_window.setWindowState(self.main_window.windowState() & ~Qt.WindowState.WindowMinimized)
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

        # 直达 OOBE 结束时选中的导航页面（按 objectName 查找）
        if navigate_to and not self.main_window.switch_to_interface(navigate_to):
            logger.warning("未找到 OOBE 请求的导航页面: %s", navigate_to)

    def run_oobe(self) -> str | None:
        """首次运行时启动设置向导

        Returns:
            向导结束后主界面应直达的页面 objectName，未指定则为 None
        """
        from EasiAuto.view.oobe import OobeWindow

        logger.info("首次运行，启动设置向导")
        window = OobeWindow()
        window.exec()
        return window.navigate_to

    def _handle_login_request_from_ui(self, automation: BaseAutomation) -> None:
        """响应从 UI 发送的自动登录执行请求"""
        if self.main_window:
            self.main_window.showMinimized()

        with self.from_ipc():
            self.start_login(Namespace(id=automation.id, manual=True))

    # ── 登录流程 ──

    def start_login(self, args: Namespace) -> bool:
        """开始登录任务

        args:
            id: str | None - 档案 ID (与 --account 互斥)
            account: str | None - 账号 (当使用 --account 时必填)
            password: str | None - 密码 (当使用 --account 时必填)
            manual: bool - 是否为手动执行 (不显示确认弹窗)
        """
        from_ipc = self._ipc_context

        if self.login_running:
            logger.warning("登录任务已在执行中, 拒绝新的 login 请求")
            return False

        if not self.preflight.ensure_profile_unlocked(self.main_window):
            logger.error("未解锁档案，自动登录中止")
            if not from_ipc:
                stop(1)
            return False

        if config.Login.SkipOnce:
            logger.info("已通过配置文件禁用, 正在退出")
            config.Login.SkipOnce = False
            if not from_ipc:
                stop()
            return False

        # 解析登录凭据
        result = cli.resolve_credentials(args)
        if result is None:
            if not from_ipc:
                stop(1)
            return False
        type, credentials = result

        # 运行前确认
        if not self.preflight.confirm(args, credentials):
            if not from_ipc:
                stop()
            return False

        self.preflight.show_banner()
        self.preflight.show_status_overlay(self._on_stop_automation)

        # 开始登录任务
        logger.debug(f"当前设置的登录方案: {config.Login.Method}")
        self._current_login_triggered_via_ipc = from_ipc

        automation_manager.run(type, credentials)

        self.login_running = True
        return True

    def _on_login_finished(self, success: bool = True, error_message: str | None = None) -> None:
        """登录结束后的回调"""
        if not self.login_running:
            return
        from_ipc = self._current_login_triggered_via_ipc
        self.login_running = False
        logger.info("登录任务已停止运行")

        # 关闭覆盖窗口
        self.preflight.teardown()

        # 发送失败通知
        if error_message:
            logger.error(f"自动登录失败: {error_message}")
            ToastNotifier().show(
                "自动登录失败",
                f"{error_message}\n检查日志以获取详细信息",
            )

        should_check_update = (
            success
            and not self.stop_requested
            and not from_ipc
            and config.Update.CheckAfterLogin
            and config.Update.Mode > UpdateMode.NEVER
        )

        if self.preflight.overlay_active:
            QTimer.singleShot(3000, lambda: self._close_status_overlay(from_ipc))

        if should_check_update:
            self._post_login_update_thread = PostLoginUpdateThread()
            self._post_login_update_thread.finished.connect(lambda: self._on_post_login_update_check_finished(from_ipc))
            self._post_login_update_thread.start()

        self._maybe_exit_after_login(from_ipc)

    def _on_login_failed(self, error_message: str) -> None:
        self._on_login_finished(success=False, error_message=error_message)

    def _close_status_overlay(self, from_ipc: bool) -> None:
        self.preflight.close_status_overlay()
        self._maybe_exit_after_login(from_ipc)

    def _on_post_login_update_check_finished(self, from_ipc: bool) -> None:
        self._post_login_update_thread = cleanup_widget(self._post_login_update_thread)
        self._maybe_exit_after_login(from_ipc)

    def _maybe_exit_after_login(self, from_ipc: bool) -> None:
        if from_ipc:
            return
        if not self.preflight.overlay_active and self._post_login_update_thread is None:
            stop()

    def _on_stop_automation(self) -> None:
        automation_manager.stop()
        self.stop_requested = True

    # ── 单实例与 IPC ──

    @contextmanager
    def from_ipc(self):
        prev_context = self._ipc_context
        self._ipc_context = True
        try:
            yield
        finally:
            self._ipc_context = prev_context

    def _handle_external_argv(self, argv: list[str]) -> None:
        """处理来自次实例的参数"""
        try:
            args = cli.build_parser().parse_args(argv[1:])
        except SystemExit:
            logger.warning(f"收到无效参数, 已忽略: {argv!r}")
            return
        command = getattr(args, "command", None)
        if command not in cli.FORWARDABLE_COMMANDS:
            logger.warning(f"忽略不被允许的 IPC 命令: {command!r}")
            return

        with self.from_ipc():
            cli.dispatch(self, args)

    def _forward_or_exit(self, command: str | None) -> None:
        """转发参数至主实例或退出"""
        if command in cli.FORWARDABLE_COMMANDS:
            ok = send_argv_to_primary(IPC_SERVER_NAME, sys.argv)
            if ok:
                logger.info(f"已将参数转发到主实例: {command}")
                stop(0)
            logger.warning("检测到已有实例, 但参数转发失败")
            stop(1)
        logger.info(f"检测到已有实例, 命令 {command!r} 不允许转发, 当前实例退出")
        stop(0)

    def _notify_updated(self, command: str | None) -> None:
        if command == "skip":
            return

        last_version: Version | None = None
        if config.Update.LastVersion != "Unknown":
            try:
                last_version = Version(config.Update.LastVersion)
            except Exception as e:
                logger.warning(f"解析上个版本时发生异常: {e}")

        if last_version is None:
            return

        if last_version < Version("1.2.0b1"):
            try:
                migrate_desktop_shortcut_icon()
            except Exception as e:
                logger.warning(f"迁移桌面快捷方式图标时发生异常: {e}")

        if last_version < Version(__version__):
            cleanup_update_cache()
            logger.success(f"应用已更新: {config.Update.LastVersion} -> {__version__}")
            ToastNotifier().show(
                f"EasiAuto 已更新至 {__version__}",
                f"已从 {config.Update.LastVersion} 更新至 {__version__}",
            )
        config.Update.LastVersion = __version__

    def run(self) -> None:
        args = cli.build_parser().parse_args()
        command = getattr(args, "command", None)

        if command == "patch":  # patch 需绕过单例检查，提前 dispatch
            cli.dispatch(self, args)
            return

        if not self.is_unique_instance():
            self._forward_or_exit(command)
            return

        if command in cli.UI_COMMANDS:
            from PySide6.QtWidgets import QApplication
            from qfluentwidgets import (
                FluentTranslator,
                Theme,
                setTheme,
                setThemeColor,
            )

            app = QApplication(sys.argv)
            translator = FluentTranslator(QLocale(QLocale.Language.Chinese))
            app.installTranslator(translator)
            setTheme(Theme(config.App.Theme.value))
            setThemeColor(BRAND)

            self.ipc_server = ArgvIpcServer(IPC_SERVER_NAME, self._handle_external_argv)
            self.ipc_server.start()
            compatibility_patches.apply_all()

        self._notify_updated(command)
        cli.dispatch(self, args)


def main() -> None:
    Launcher().run()
