"""主密码输入对话框（模态）—— 用于登录等无窗口场景下的手动解锁确认"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    BodyLabel,
    MessageBoxBase,
    PasswordLineEdit,
    SubtitleLabel,
)

from EasiAuto.view.tokens import TEXT_SECONDARY_DARK, TEXT_SECONDARY_LIGHT

# 密码错误提示色
ERROR_COLOR_LIGHT = "#C42B1C"
ERROR_COLOR_DARK = "#FF99A4"


class MasterPasswordDialog(MessageBoxBase):
    """模态主密码对话框。

    ``verify`` 回调用于在确认时校验主密码；返回 False 时保持对话框打开并显示错误。
    确认成功后可通过 ``get_password()`` 取得输入的主密码。
    """

    def __init__(
        self,
        title: str,
        description: str = "",
        verify: Callable[[str], bool] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self._verify = verify
        self._password: str | None = None

        self.titleLabel = SubtitleLabel(title, self)
        self.desc_label = BodyLabel(description, self)
        self.desc_label.setTextColor(QColor(TEXT_SECONDARY_LIGHT), QColor(TEXT_SECONDARY_DARK))
        self.desc_label.setWordWrap(True)

        self.password_edit = PasswordLineEdit(self)
        self.password_edit.setPlaceholderText("请输入主密码")

        self.error_label = BodyLabel("", self)
        self.error_label.setTextColor(QColor(ERROR_COLOR_LIGHT), QColor(ERROR_COLOR_DARK))
        self.error_label.setVisible(False)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.desc_label)
        self.viewLayout.addWidget(self.password_edit)
        self.viewLayout.addWidget(self.error_label)

        self.widget.setMinimumWidth(360)
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.password_edit.returnPressed.connect(self.yesButton.click)
        self.password_edit.setFocus()

    def validate(self) -> bool:
        """确认前校验主密码；错误时显示提示并保持对话框打开。"""
        pwd = self.password_edit.text()
        if not pwd:
            self._show_error("请输入主密码")
            return False
        if self._verify is not None and not self._verify(pwd):
            self._show_error("主密码错误，请重新输入")
            return False
        self.error_label.setVisible(False)
        self._password = pwd
        return True

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    def get_password(self) -> str | None:
        return self._password
