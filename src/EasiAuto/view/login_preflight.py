"""登录前置流程：档案解锁、运行前确认弹窗、警示横幅与状态浮窗

把登录期间会出现在屏幕上的临时 UI 集中在此，负责其创建与回收；
调用方（Launcher）只负责流程与退出策略。
"""

from __future__ import annotations

import time
from argparse import Namespace
from collections.abc import Callable
from typing import Any, assert_never

from loguru import logger

from PySide6.QtWidgets import QWidget

from EasiAuto.core.display import (
    Point,
    calc_relative_login_window_position,
    get_scale,
    get_screen_size,
    get_screen_size_physical,
)
from EasiAuto.core.security import is_master_key_unlocked
from EasiAuto.models.config import config
from EasiAuto.models.profile import profile
from EasiAuto.view.components import (
    DialogResponse,
    PreRunPopup,
    PrivacyMask,
    SmallStatusOverlay,
    StatusOverlay,
    StatusOverlayBase,
    WarningBanner,
)
from EasiAuto.view.helpers import cleanup_widget


class LoginPreflight:
    """登录前置步骤与临时 UI 的持有者

    Attributes:
        banner: 警示横幅
        status_overlay: 状态浮窗
        privacy_mask: 隐私保护遮罩
    """

    def __init__(self) -> None:
        self.banner: WarningBanner | None = None
        self.status_overlay: StatusOverlayBase | None = None
        self.privacy_mask: PrivacyMask | None = None
        self._unlock_host: QWidget | None = None

    # ── 前置步骤 ──

    def ensure_profile_unlocked(self, parent: QWidget | None) -> bool:
        """确保已加密的档案在本次登录前处于解锁状态

        优先使用本机缓存静默解锁；缓存不可用时弹出主密码对话框。

        Args:
            parent (QWidget | None): 对话框宿主窗口

        Returns:
            bool: 可以继续登录时为 True
        """
        if not profile.encryption_enabled or is_master_key_unlocked():
            return True

        if profile.read_cached_unlock():
            logger.info("自动登录已从本机缓存自动解锁档案")
            return True

        return self._prompt_master_password(parent)

    def _prompt_master_password(self, parent: QWidget | None) -> bool:
        """弹出主密码对话框；成功后已解锁会话并写入本机缓存"""
        from EasiAuto.view.components.master_password_dialog import MasterPasswordDialog

        if parent is None:
            if self._unlock_host is None:
                self._unlock_host = QWidget()
            parent = self._unlock_host

        dialog = MasterPasswordDialog(
            title="解锁档案",
            description="自动登录需要读取账号密码，请输入主密码解锁",
            verify=profile.unlock_master_password,
            parent=parent,
        )
        dialog.exec()
        return dialog.get_password() is not None

    def confirm(self, launch_args: Namespace, credentials: Any) -> bool:
        """运行前确认：显示警告弹窗并等待用户选择

        Args:
            launch_args: 命令行参数（用于取显示名与 manual 标记）
            credentials: 已解析的凭据，形如 (账号, 密码)

        Returns:
            bool: 应继续登录时为 True（用户取消时为 False；弹窗异常时按继续处理）
        """
        if not config.Warning.Enabled or getattr(launch_args, "manual", False):
            return True

        try:
            msgbox = PreRunPopup()
            display_name = self._resolve_display_name(launch_args, credentials)
            if display_name:
                msgbox.set_account_name(display_name)

            delays = 0
            while True:
                if delays >= config.Warning.MaxDelays:
                    msgbox.delay_btn.hide()
                match msgbox.countdown(config.Warning.Timeout):
                    case DialogResponse.CANCEL:
                        logger.info("用户取消操作, 正在退出")
                        return False
                    case DialogResponse.CONTINUE:
                        logger.info("用户确认继续, 继续执行")
                        return True
                    case DialogResponse.TIMEOUT:
                        logger.info("等待超时, 继续执行")
                        return True
                    case DialogResponse.DELAY:
                        logger.info(f"用户选择推迟, 等待 {config.Warning.DelayTime} 秒...")
                        delays += 1
                        time.sleep(config.Warning.DelayTime)
                    case unreachable:
                        assert_never(unreachable)
        except Exception:
            logger.error("显示警告弹窗时出错, 跳过警告")
            return True

    @staticmethod
    def _resolve_display_name(launch_args: Namespace, credentials: Any) -> str:
        """警告弹窗中展示的账号名：优先档案自定义名称，其次账号本身"""
        display_name = ""
        if config.Warning.ShowUserName:
            if getattr(launch_args, "id", None):
                auto = profile.get_automation(launch_args.id)
                if auto:
                    display_name = auto.display_name or ""
            if not display_name and isinstance(credentials, tuple):
                display_name = credentials[0]
        return display_name

    # ── 临时 UI ──

    def show_banner(self) -> None:
        """显示警示横幅；失败时跳过"""
        if not config.Banner.Enabled:
            return

        try:
            width = get_screen_size()[0]
            self.banner = WarningBanner(config.Banner.Style)
            self.banner.setGeometry(0, 80, width, 140)
            self.banner.show()
        except Exception as e:
            logger.error(f"显示横幅时出错, 跳过横幅: {e}")

    def show_status_overlay(self, on_stop: Callable[[], None]) -> None:
        """显示状态浮窗并接上登录状态信号；失败时跳过

        Args:
            on_stop (Callable[[], None]): 用户点击浮窗停止按钮时的回调
        """
        if not config.StatusOverlay.Enabled:
            return

        try:
            self.status_overlay = StatusOverlay() if self._available_space() > 300 else SmallStatusOverlay()
            self.status_overlay.stop_clicked.connect(on_stop)
            self._bind_overlay(self.status_overlay)
        except Exception as e:
            self.status_overlay = None
            logger.error(f"设置状态浮窗时出错, 跳过状态浮窗: {e}")

    @staticmethod
    def _available_space() -> float:
        """估算登录窗口下方可用于摆放状态浮窗的空间（像素）"""
        try:
            # 根据屏幕高度和登录窗口位置选择状态浮窗的大小
            expected_pos = Point(config.Login.Position.AgreementCheckbox)
            expected_pos.y += 8
            login_window_bottom = calc_relative_login_window_position(
                expected_pos,
                window_size=config.Login.Position.LoginWindowSize,
                base_size=config.Login.Position.BaseSize,
            ).y
            return get_screen_size_physical()[1] - (login_window_bottom + 8)
        except Exception as e:
            logger.warning(f"计算状态浮窗位置时出错: {e}")
            return 0

    @staticmethod
    def _bind_overlay(overlay: StatusOverlayBase) -> None:
        """把自动化管理器的状态信号接到浮窗上"""
        from EasiAuto.services.automation import automation_manager

        automation_manager.started.connect(overlay.show)
        automation_manager.succeeded.connect(overlay.on_success)
        automation_manager.interrupted.connect(overlay.on_interrupted)
        automation_manager.failed.connect(overlay.on_failed)
        automation_manager.task_updated.connect(overlay.set_task_text)
        automation_manager.progress_updated.connect(overlay.set_progress_text)

    def show_privacy_mask(self, x: int, y: int, w: int, h: int) -> None:
        """显示隐私保护遮罩（输入为绝对坐标）"""
        scale = get_scale()
        if self.privacy_mask is None:
            self.privacy_mask = PrivacyMask()
        # 由于 Qt 自带缩放，所以要将缩放重新转换为 100%
        self.privacy_mask.setGeometry(int(x / scale), int(y / scale), int(w / scale), int(h / scale))
        self.privacy_mask.show()

    def hide_privacy_mask(self) -> None:
        """隐藏隐私保护遮罩"""
        self.privacy_mask = cleanup_widget(self.privacy_mask)

    # ── 回收 ──

    @property
    def overlay_active(self) -> bool:
        """状态浮窗是否仍在显示"""
        return self.status_overlay is not None

    def teardown(self) -> None:
        """登录结束后立即回收横幅与隐私遮罩"""
        self.banner = cleanup_widget(self.banner)
        self.hide_privacy_mask()

    def close_status_overlay(self) -> None:
        """关闭状态浮窗"""
        self.status_overlay = cleanup_widget(self.status_overlay)
