from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, InfoBar, LineEdit, PrimaryPushButton, StrongBodyLabel, SubtitleLabel

from ._shared import resolve_token, set_token


class ConfigWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ConfigWidget")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        layout.addWidget(SubtitleLabel("配置", self))

        layout.addWidget(StrongBodyLabel("GitHub Token", self))
        self.token_edit = LineEdit(self)
        self.token_edit.setPlaceholderText("输入 GitHub Token（不持久化）")
        self.token_edit.setEchoMode(LineEdit.EchoMode.Password)

        existing = resolve_token()
        if existing:
            self.token_edit.setText(existing)

        layout.addWidget(self.token_edit)

        self.apply_btn = PrimaryPushButton("应用", self)
        self.apply_btn.setIcon(FluentIcon.ACCEPT)
        self.apply_btn.clicked.connect(self._apply_token)
        layout.addWidget(self.apply_btn)

        layout.addStretch(1)

        layout.addWidget(StrongBodyLabel("提示", self))
        hint = StrongBodyLabel("Token 仅存储在内存中，重启后需要重新输入。也可以设置 RELEASE_PAT 环境变量。", self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _apply_token(self):
        value = self.token_edit.text().strip()
        if value:
            set_token(value)
            InfoBar.success("成功", "Token 已应用", parent=self)
        else:
            InfoBar.warning("提示", "Token 不能为空", parent=self)
