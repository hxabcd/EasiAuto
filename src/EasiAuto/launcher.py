import sys
import time
from argparse import ArgumentParser, Namespace
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import assert_never

import windows11toast
from loguru import logger
from packaging.version import Version

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentTranslator,
    Theme,
    setTheme,
    setThemeColor,
)

from EasiAuto import __version__
from EasiAuto.common.config import DownloadSource, UpdateMode, config
from EasiAuto.common.consts import IPC_SERVER_NAME
from EasiAuto.common.profile import profile
from EasiAuto.common.runtime import ArgvIpcServer, check_singleton, init_exception_handler, send_argv_to_primary
from EasiAuto.common.update import UpdateError, cleanup_update_cache, update_checker
from EasiAuto.common.utils import (
    Point,
    calc_relative_login_window_position,
    get_resource,
    get_screen_size,
    get_screen_size_physical,
    init_exit_signal_handlers,
    stop,
)
from EasiAuto.core.automator.manager import automation_manager
from EasiAuto.view.components import (
    DialogResponse,
    PreRunPopup,
    SmallStatusOverlay,
    StatusOverlay,
    StatusOverlayBase,
    WarningBanner,
)
from EasiAuto.view.main_window import MainWindow

UI_COMMANDS = {None, "settings"}
FORWARDABLE_COMMANDS = {"login", "skip"}

init_exception_handler()
init_exit_signal_handlers()

app = QApplication(sys.argv)
translator = FluentTranslator()
app.installTranslator(translator)
setTheme(Theme(config.App.Theme.value))
setThemeColor("#00C884")

app.aboutToQuit.connect(update_checker.shutdown)


class PostLoginUpdateThread(QThread):
    def run(self) -> None:
        try:
            decision = update_checker.check()
            if decision.available and decision.downloads:
                if config.Update.Mode >= UpdateMode.CHECK_AND_INSTALL:
                    file = update_checker.download_update(decision.downloads[0], allow_latency_check=True)
                    update_checker.apply_script(file, reopen=False)
                else:
                    windows11toast.notify(
                        title="更新可用",
                        body=f"新版本：{decision.target_version}\n打开应用查看详细信息",
                        icon_placement=windows11toast.IconPlacement.APP_LOGO_OVERRIDE,
                        icon_hint_crop=windows11toast.IconCrop.NONE,
                        icon_src=get_resource("icons/EasiAuto.ico"),
                    )
        except UpdateError as e:
            logger.warning(f"检查更新时发生异常, 已跳过: {e}")
        except Exception as e:
            logger.error(f"检查更新时发生未预期异常, 已跳过: {e}")


class Launcher:
    def __init__(self) -> None:
        self.main_window: MainWindow | None = None
        self.banner: WarningBanner | None = None
        self.status_overlay: StatusOverlayBase | None = None

        self.login_running: bool = False
        self.stop_requested: bool = False

        self.ipc_server: ArgvIpcServer | None = None
        self._ipc_context: bool = False
        self._current_login_triggered_via_ipc: bool = False
        self._post_login_overlay_done: bool = False
        self._post_login_update_done: bool = False
        self._post_login_update_thread: PostLoginUpdateThread | None = None
        automation_manager.finished.connect(self._on_login_finished)
        automation_manager.failed.connect(self._on_login_failed)

        # TODO: 考虑简化状态

    def _show_settings_window(self) -> None:
        if self.main_window is None:
            self.main_window = MainWindow()
            self.main_window.runAutomation.connect(self._handle_login_request_from_ui)
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _handle_login_request_from_ui(self, account: str, password: str) -> None:
        """响应从 UI 发送的自动登录执行请求"""
        if self.main_window:
            self.main_window.showMinimized()

        with self.from_ipc():
            self._start_login(
                Namespace(
                    account=account,
                    password=password,
                    manual=True,
                    id=None,
                )
            )

    def _build_parser(self) -> ArgumentParser:
        parser = ArgumentParser(prog="EasiAuto", description="一款自动登录希沃白板的小工具")
        subparsers = parser.add_subparsers(title="子命令", dest="command")

        login_parser = subparsers.add_parser("login", help="登录账号")
        login_target_group = login_parser.add_mutually_exclusive_group(required=True)
        login_target_group.add_argument("-i", "--id", help="档案 ID")
        login_target_group.add_argument("-a", "--account", help="账号")
        login_parser.add_argument("-p", "--password", help="密码（当使用 --account 时必填）")
        login_parser.add_argument("-m", "--manual", action="store_true", help="手动执行（不显示确认弹窗）")

        subparsers.add_parser("settings", help="打开设置界面")
        subparsers.add_parser("skip", help="跳过下一次登录")
        return parser

    def _on_login_finished(self, success: bool = True, error_message: str | None = None) -> None:
        """登录结束后的回调"""
        if not self.login_running:
            return
        from_ipc = self._current_login_triggered_via_ipc
        self.login_running = False
        logger.info("登录任务已停止运行")

        # 关闭警示横幅
        if self.banner is not None:
            self.banner.close()
            self.banner.deleteLater()
            self.banner = None

        self._current_login_triggered_via_ipc = False

        # 发送失败通知
        if error_message:
            logger.error(f"自动登录失败: {error_message}")
            windows11toast.notify(
                title="自动登录失败",
                body=f"{error_message}\n检查日志以获取详细信息",
                icon_placement=windows11toast.IconPlacement.APP_LOGO_OVERRIDE,
                icon_hint_crop=windows11toast.IconCrop.NONE,
                icon_src=get_resource("icons/EasiAuto.ico"),
            )

        self._post_login_overlay_done = self.status_overlay is None
        self._post_login_update_done = any(  # 以下情况不触发更新检查
            (
                not success,  # 登录失败
                self.stop_requested,  # 登录中止
                from_ipc,  # 通过 IPC 触发
                not (config.Update.CheckAfterLogin and config.Update.Mode > UpdateMode.NEVER),
            )
        )

        if not self._post_login_overlay_done:
            QTimer.singleShot(3000, lambda: self._close_status_overlay(from_ipc))

        if not self._post_login_update_done:
            self._post_login_update_thread = PostLoginUpdateThread()
            self._post_login_update_thread.finished.connect(lambda: self._on_post_login_update_check_finished(from_ipc))
            self._post_login_update_thread.start()

        self._maybe_exit_after_login(from_ipc)

    def _on_login_failed(self, error_message: str) -> None:
        self._on_login_finished(success=False, error_message=error_message)

    def _close_status_overlay(self, from_ipc: bool) -> None:
        if self.status_overlay is not None:
            self.status_overlay.close()
            self.status_overlay.deleteLater()
            self.status_overlay = None
        self._post_login_overlay_done = True
        self._maybe_exit_after_login(from_ipc)

    def _on_post_login_update_check_finished(self, from_ipc: bool) -> None:
        if self._post_login_update_thread is not None:
            self._post_login_update_thread.deleteLater()
            self._post_login_update_thread = None
        self._post_login_update_done = True
        self._maybe_exit_after_login(from_ipc)

    def _maybe_exit_after_login(self, from_ipc: bool) -> None:
        if from_ipc:
            return
        if self._post_login_overlay_done and self._post_login_update_done:
            stop()

    def _on_stop_automation(self) -> None:
        automation_manager.stop()
        self.stop_requested = True

    def _resolve_login_credentials(self, args: Namespace) -> tuple[str, str] | None:
        if args.id:
            auto = profile.get_automation(args.id)
            if auto is None:
                logger.error(f"未找到档案 ID: {args.id}")
                return None
            if not auto.enabled:
                logger.warning(f"档案 {args.id} 已被禁用")
                return None
            if auto.account == "" or auto.password == "":
                logger.error(f"档案 {args.id} 的账号或密码为空")
                return None
            return auto.account, auto.password

        if args.account and args.password:
            return args.account, args.password

        logger.error("参数错误: 使用 --account 时必须同时提供 --password")
        return None

    def _start_login(self, args: Namespace) -> bool:
        """开始登录任务"""

        from_ipc = self._ipc_context

        if self.login_running:
            logger.warning("登录任务已在执行中, 拒绝新的 login 请求")
            return False

        if config.Login.SkipOnce:
            logger.info("已通过配置文件禁用, 正在退出")
            config.Login.SkipOnce = False
            if not from_ipc:
                stop()
            return False

        # 解析登录凭据
        credentials = self._resolve_login_credentials(args)
        if credentials is None:
            if not from_ipc:
                stop(1)
            return False

        # 显示警告弹窗
        if config.Warning.Enabled and not args.manual:
            try:
                msgbox = PreRunPopup()
                delays = 0
                while True:
                    if delays >= config.Warning.MaxDelays:
                        msgbox.delay_btn.hide()
                    response = msgbox.countdown(config.Warning.Timeout)
                    match response:
                        case DialogResponse.CANCEL:
                            logger.info("用户取消操作, 正在退出")
                            if not from_ipc:
                                stop()
                            return False
                        case DialogResponse.CONTINUE:
                            logger.info("用户确认继续, 继续执行")
                            break
                        case DialogResponse.TIMEOUT:
                            logger.info("等待超时, 继续执行")
                            break
                        case DialogResponse.DELAY:
                            logger.info(f"用户选择推迟, 等待 {config.Warning.DelayTime} 秒...")
                            delays += 1
                            time.sleep(config.Warning.DelayTime)
                            continue
                        case unreachable:
                            assert_never(unreachable)
            except Exception:
                logger.error("显示警告弹窗时出错, 跳过警告")

        # 显示警示横幅
        if config.Banner.Enabled:
            try:
                width = get_screen_size()[0]
                self.banner = WarningBanner(config.Banner.Style)
                self.banner.setGeometry(0, 80, width, 140)
                self.banner.show()
            except Exception as e:
                logger.error(f"显示横幅时出错, 跳过横幅: {e}")

        # 显示状态浮窗
        if config.StatusOverlay.Enabled:
            try:
                try:
                    # 根据屏幕高度和登录窗口位置选择状态浮窗的大小
                    screen_height = get_screen_size_physical()[1]
                    expected_pos = Point(config.Login.Position.AgreementCheckbox)
                    expected_pos.y += 8
                    login_window_buttom = calc_relative_login_window_position(
                        expected_pos,
                        window_size=config.Login.Position.LoginWindowSize,
                        base_size=config.Login.Position.BaseSize,
                    ).y
                    available_space = screen_height - (login_window_buttom + 8)
                except Exception as e:
                    logger.warning(f"计算状态浮窗位置时出错: {e}")
                    available_space = 0

                self.status_overlay = StatusOverlay() if available_space > 300 else SmallStatusOverlay()
                self.status_overlay.stop_clicked.connect(self._on_stop_automation)
                automation_manager.started.connect(self.status_overlay.show)
                automation_manager.successed.connect(self.status_overlay.on_success)
                automation_manager.interrupted.connect(self.status_overlay.on_interrupted)
                automation_manager.failed.connect(self.status_overlay.on_failed)
                automation_manager.task_updated.connect(self.status_overlay.set_task_text)
                automation_manager.progress_updated.connect(self.status_overlay.set_progress_text)
            except Exception as e:
                logger.error(f"设置状态浮窗时出错, 跳过状态浮窗: {e}")

        # 开始登录任务
        logger.debug(f"当前设置的登录方案: {config.Login.Method}")
        self._current_login_triggered_via_ipc = from_ipc

        automation_manager.run(*credentials)

        self.login_running = True
        return True

    def cmd_login(self, args: Namespace) -> bool:
        """login 子命令 - 执行自动登录"""
        if not self._start_login(args):
            return False

        if not self._ipc_context:
            sys.exit(app.exec())
        return True

    def cmd_settings(self, _) -> None:
        """settings 子命令 - 打开设置界面"""
        if config.Update.TargetDownloadSource == DownloadSource.AUTO:
            update_checker.init_latency()

        self._show_settings_window()
        if not self._ipc_context:
            sys.exit(app.exec())

    def cmd_skip(self, _) -> None:
        """skip 子命令 - 跳过下一次登录"""
        config.Login.SkipOnce = True
        if self._ipc_context:
            logger.success("已更新配置文件")
            return

        logger.success("已更新配置文件, 正在退出")
        stop()

    def _dispatch_command(self, args: Namespace) -> None:
        command = getattr(args, "command", None)
        match command:
            case "login":
                self.cmd_login(args)
            case "skip":
                self.cmd_skip(args)
            case _:
                self.cmd_settings(args)

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
        parser = self._build_parser()
        try:
            args = parser.parse_args(argv[1:])
        except SystemExit:
            logger.warning(f"收到无效参数, 已忽略: {argv!r}")
            return
        if (command := getattr(args, "command", None)) not in FORWARDABLE_COMMANDS:
            logger.warning(f"忽略不被允许的 IPC 命令: {command!r}")
            return
        with self.from_ipc():
            self._dispatch_command(args)

    def _forward_or_exit(self, command: str | None) -> None:
        """转发参数至主实例或退出"""
        if command in FORWARDABLE_COMMANDS:
            forwarded = send_argv_to_primary(IPC_SERVER_NAME, sys.argv)
            if forwarded:
                logger.info(f"已将参数转发到主实例: {command}")
                stop(0)
            logger.warning("检测到已有实例, 但参数转发失败")
            stop(1)

        logger.info(f"检测到已有实例, 命令 {command!r} 不允许转发, 当前实例退出")
        stop(0)

    def _notify_updated(self, command: str | None) -> None:
        if command == "skip":
            return

        if config.Update.LastVersion != "Unknown":
            try:
                last_version = Version(config.Update.LastVersion)
            except Exception as e:
                logger.warning(f"解析上个版本时发生异常: {e}")
            else:
                if last_version < Version(__version__):
                    cleanup_update_cache()
                    windows11toast.notify(
                        title=f"已更新至 {__version__}",
                        body=f"{config.Update.LastVersion} -> {__version__}",
                        icon_placement=windows11toast.IconPlacement.APP_LOGO_OVERRIDE,
                        icon_hint_crop=windows11toast.IconCrop.NONE,
                        icon_src=get_resource("icons/EasiAuto.ico"),
                    )
        config.Update.LastVersion = __version__

    def run(self) -> None:
        parser = self._build_parser()
        args = parser.parse_args()
        command = getattr(args, "command", None)

        if not check_singleton(focus_existing=(command == "settings")):
            self._forward_or_exit(command)
            return

        if command in UI_COMMANDS:
            self.ipc_server = ArgvIpcServer(IPC_SERVER_NAME, self._handle_external_argv)
            self.ipc_server.start()

        self._notify_updated(command)
        self._dispatch_command(args)

        config.Internal.Statistics.TotalRunTime += (
            datetime.now(UTC) - config.Internal.Statistics.ThisInstanceLaunchTime
        ).total_seconds()


def main() -> None:
    Launcher().run()
