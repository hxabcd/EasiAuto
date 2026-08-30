"""档案页状态栏与高级选项对话框组件"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    IconWidget,
    MessageBoxBase,
    SubtitleLabel,
    TransparentPushButton,
)

from EasiAuto.models.profile import profile
from EasiAuto.view.tokens import BRAND, TEXT_SECONDARY_DARK, TEXT_SECONDARY_LIGHT

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
            card_type=SettingCardType.SWITCH,
            icon=FluentIcon.VPN,
            title="启用档案密码加密",
            content="保存档案时对密码加密",
            is_item=True,
            item_margin=False,
        )
        self.encrypt_card.setChecked(profile.encryption_enabled)
        self.encrypt_card.valueChanged.connect(self._on_encryption_changed)
        self.vBoxLayout.addWidget(self.encrypt_card)

    def _on_encryption_changed(self, checked: bool):
        profile.encryption_enabled = checked
        profile.save(reason="encryption_changed")


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
        """根据当前加密设置刷新提示可见性"""
        self.encrypt_hint.setVisible(profile.encryption_enabled)

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
