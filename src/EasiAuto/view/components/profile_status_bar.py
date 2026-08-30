"""档案页状态栏与高级选项对话框组件"""

from __future__ import annotations

from typing import cast

from loguru import logger

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    IconWidget,
    MessageBoxBase,
    PushButton,
    SubtitleLabel,
    TransparentPushButton,
)

from EasiAuto.core import security
from EasiAuto.models.profile import profile
from EasiAuto.view.tokens import BRAND, TEXT_SECONDARY_DARK, TEXT_SECONDARY_LIGHT

from .master_password_flyout import show_master_password_flyout
from .setting_card import CardType as SettingCardType
from .setting_card import SettingCard


class AdvancedOptionsDialog(MessageBoxBase):
    """高级选项"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("高级选项", self)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)

        # 初始化设置项
        self._init_settings()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.view)

        self.widget.setMinimumWidth(400)
        self.yesButton.setText("关闭")
        self.yesButton.clicked.connect(self.accept)
        self.cancelButton.hide()

    def _init_settings(self):
        """初始化设置项"""
        self.encrypt_card = SettingCard(
            card_type=SettingCardType.BUTTON,
            icon=FluentIcon.VPN,
            title="档案密码加密",
            content="使用主密码加密保存的账号密码",
            is_item=True,
            item_margin=False,
        )
        self.encrypt_card.clicked.connect(self._on_encryption_clicked)
        self.encrypt_button = cast(PushButton, self.encrypt_card.widget)
        self.vBoxLayout.addWidget(self.encrypt_card)

        # 独立设置项：仅启用加密时可用
        self.passwordless_card = SettingCard(
            card_type=SettingCardType.SWITCH,
            icon=FluentIcon.FINGERPRINT,
            title="在本机免密查看档案密码",
            content="开启后，打开档案页无需输入主密码即可查看密码",
            is_item=True,
            item_margin=False,
        )
        self.passwordless_card.valueChanged.connect(self._on_passwordless_changed)
        self.vBoxLayout.addWidget(self.passwordless_card)

        self._refresh_encrypt_card()

    def _refresh_encrypt_card(self):
        """根据当前加密状态刷新按钮与描述"""
        enabled = profile.encryption_enabled
        self.encrypt_card.setContent(
            "保存档案时使用主密码加密账号密码" if enabled else "未启用加密，档案中的密码明文保存"
        )
        self.encrypt_button.setText("禁用" if enabled else "启用")
        # 未启用加密时关闭并禁用「免密查看」
        self.passwordless_card.setEnabled(enabled)
        self.passwordless_card.setChecked(enabled and profile.passwordless_view)

    def _on_passwordless_changed(self, checked: bool):
        if not profile.encryption_enabled or not security.is_master_key_unlocked():
            return
        if profile.passwordless_view == checked:
            return
        profile.passwordless_view = checked
        profile.save(reason="encryption_changed")

    def _on_encryption_clicked(self):
        if profile.encryption_enabled:
            self._disable_encryption()
        else:
            self._enable_encryption()

    def _enable_encryption(self):
        show_master_password_flyout(
            target=self.encrypt_button,
            parent=self,
            title="设置主密码",
            description="设置用于加密账号密码的主密码，保护隐私安全。忘记后将无法找回，请牢记密码",
            require_confirm=True,
            confirm_text="启用加密",
            on_confirm=self._apply_enable_encryption,
        )

    def _apply_enable_encryption(self, master_password: str) -> str | None:
        try:
            profile.enable_encryption(master_password)
        except Exception as e:
            logger.error(f"启用档案加密失败: {e}")
            return "启用加密失败，请重试"
        self._refresh_encrypt_card()
        return None

    def _disable_encryption(self):
        show_master_password_flyout(
            target=self.encrypt_button,
            parent=self,
            title="关闭加密",
            description="请输入当前主密码以关闭加密，档案中的密码将恢复为明文",
            require_confirm=False,
            confirm_text="关闭加密",
            on_confirm=self._apply_disable_encryption,
        )

    def _apply_disable_encryption(self, master_password: str) -> str | None:
        try:
            ok = profile.disable_encryption(master_password)
        except Exception as e:
            logger.error(f"关闭档案加密失败: {e}")
            return "关闭加密失败，请重试"
        if not ok:
            return "主密码错误，请重新输入"
        self._refresh_encrypt_card()
        return None


class ProfileStatusBar(QWidget):
    """档案页状态栏"""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(54)

        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(16, 0, 16, 0)

        self.option_button = TransparentPushButton(icon=FluentIcon.DEVELOPER_TOOLS, text="高级选项")
        self.option_button.clicked.connect(self._show_advanced_options)

        layout.addWidget(SubtitleLabel("档案编辑"))

        # 加密提示：左侧图标，右侧文本，右对齐
        self.encrypt_hint = QWidget(self)
        hint_layout = QHBoxLayout(self.encrypt_hint)
        hint_layout.setContentsMargins(0, 0, 0, 0)
        hint_layout.setSpacing(4)
        self.encrypt_icon = IconWidget(FluentIcon.VPN.colored(QColor(BRAND), QColor(BRAND)))
        self.encrypt_icon.setFixedSize(16, 16)
        self.encrypt_label = BodyLabel("账号已加密存储在本地")
        self.encrypt_label.setTextColor(QColor(TEXT_SECONDARY_LIGHT), QColor(TEXT_SECONDARY_DARK))
        self.encrypt_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        hint_layout.addWidget(self.encrypt_icon)
        hint_layout.addWidget(self.encrypt_label)

        layout.addSpacing(16)
        layout.addWidget(self.encrypt_hint, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        layout.addWidget(self.option_button)

        profile.notifier.changed.connect(self._on_profile_changed)
        self._refresh_encryption_hint()

    def _on_profile_changed(self, reason: str):
        if reason == "encryption_changed":
            self._refresh_encryption_hint()

    def _refresh_encryption_hint(self):
        """根据当前加密与解锁状态刷新提示可见性"""
        if profile.encryption_enabled:
            if security.is_master_key_unlocked():
                self.encrypt_icon.setIcon(FluentIcon.VPN.colored(QColor(BRAND), QColor(BRAND)))
                self.encrypt_label.setText("账号已加密存储在本地")
            else:
                self.encrypt_icon.setIcon(FluentIcon.FINGERPRINT.colored(QColor(BRAND), QColor(BRAND)))
                self.encrypt_label.setText("档案已锁定，请输入主密码解锁")
            self.encrypt_hint.setVisible(True)
        else:
            self.encrypt_hint.setVisible(False)

    def set_compact_mode(self, compact: bool):
        """精简模式：隐藏右侧高级选项按钮与加密提示，仅保留左侧标题"""
        if compact:
            self.encrypt_hint.hide()
            self.option_button.hide()
        else:
            self._refresh_encryption_hint()
            self.option_button.show()

    def _show_advanced_options(self):
        dialog = AdvancedOptionsDialog(self.window())
        dialog.exec()
