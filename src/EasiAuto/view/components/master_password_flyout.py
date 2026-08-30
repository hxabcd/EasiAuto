"""主密码输入弹出组件（Flyout）

用于档案加密启用/禁用以及会话解锁时的密码输入。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    FluentStyleSheet,
    Flyout,
    FlyoutViewBase,
    PasswordLineEdit,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
)

from EasiAuto.view.tokens import TEXT_SECONDARY_DARK, TEXT_SECONDARY_LIGHT

# 密码错误提示色
ERROR_COLOR_LIGHT = "#C42B1C"
ERROR_COLOR_DARK = "#FF99A4"


class MasterPasswordFlyout(FlyoutViewBase):
    """主密码输入视图：标题 + 描述 + 密码输入（可选二次确认）+ 操作按钮"""

    confirmed = Signal(str)  # 用户确认后携带输入的主密码
    cancelled = Signal()

    def __init__(
        self,
        title: str,
        description: str = "",
        require_confirm: bool = False,
        confirm_text: str = "确定",
        parent=None,
    ):
        super().__init__(parent=parent)
        self.require_confirm = require_confirm

        FluentStyleSheet.TEACHING_TIP.apply(self)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(8)

        self.title_label = SubtitleLabel(title, self)
        self.desc_label = BodyLabel(description, self)
        self.desc_label.setTextColor(QColor(TEXT_SECONDARY_LIGHT), QColor(TEXT_SECONDARY_DARK))
        self.desc_label.setWordWrap(True)

        self.password_edit = PasswordLineEdit(self)
        self.password_edit.setFixedWidth(300)
        self.password_edit.setClearButtonEnabled(True)
        self.password_edit.setPlaceholderText("请输入主密码")

        self.confirm_edit: PasswordLineEdit | None = None
        if self.require_confirm:
            self.confirm_edit = PasswordLineEdit(self)
            self.confirm_edit.setFixedWidth(300)
            self.confirm_edit.setClearButtonEnabled(True)
            self.confirm_edit.setPlaceholderText("请再次输入主密码")

        self.error_label = BodyLabel("", self)
        self.error_label.setTextColor(QColor(ERROR_COLOR_LIGHT), QColor(ERROR_COLOR_DARK))
        self.error_label.setVisible(False)

        self.cancel_button = PushButton("取消", self)
        self.ok_button = PrimaryPushButton(confirm_text, self)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)

        self._layout.addWidget(self.title_label)
        self._layout.addWidget(self.desc_label)
        self._layout.addSpacing(4)
        self._layout.addWidget(self.password_edit)
        if self.confirm_edit:
            self._layout.addWidget(self.confirm_edit)
        self._layout.addWidget(self.error_label)
        self._layout.addLayout(button_row)

        self.password_edit.returnPressed.connect(self._on_confirm_clicked)
        if self.confirm_edit:
            self.confirm_edit.returnPressed.connect(self._on_confirm_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.ok_button.clicked.connect(self._on_confirm_clicked)

    def set_error(self, message: str) -> None:
        """显示校验错误信息"""
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    def _on_confirm_clicked(self):
        password = self.password_edit.text()
        if not password:
            self.set_error("请输入主密码")
            return
        if self.confirm_edit is not None and password != self.confirm_edit.text():
            self.set_error("两次输入的主密码不一致")
            return
        self.error_label.setVisible(False)
        self.confirmed.emit(password)

    def _on_cancel_clicked(self):
        self.cancelled.emit()


def show_master_password_flyout(
    target,
    parent,
    *,
    title: str,
    description: str = "",
    require_confirm: bool = False,
    confirm_text: str = "确定",
    on_confirm: Callable[[str], str | None],
) -> Flyout:
    """显示主密码输入 Flyout 并等待确认

    Parameters
    ----------
    target: QWidget | QPoint
        Flyout 锚定的目标控件或位置
    on_confirm: 校验回调，返回错误信息时保持 Flyout 打开并显示，返回 None 表示成功关闭
    """
    view = MasterPasswordFlyout(
        title=title,
        description=description,
        require_confirm=require_confirm,
        confirm_text=confirm_text,
    )
    flyout = Flyout.make(view, target=target, parent=parent)

    def _handle_confirm(password: str):
        error = on_confirm(password)
        if error:
            view.set_error(error)
            return
        flyout.close()

    view.confirmed.connect(_handle_confirm)
    view.cancelled.connect(flyout.close)
    view.password_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    return flyout
