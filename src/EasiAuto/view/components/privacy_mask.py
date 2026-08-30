from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    IconWidget,
    TitleLabel,
)

from EasiAuto.view.tokens import BRAND, TEXT_MUTED


class PrivacyMask(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )

        self.setStyleSheet("background-color: white; color: black;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_container = QHBoxLayout()
        icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_icon = IconWidget(FluentIcon.VPN.colored(BRAND, BRAND))  # type: ignore
        hint_icon.setFixedSize(64, 64)
        icon_container.addWidget(hint_icon)

        hint_label = TitleLabel("正在登录")
        hint_desc = BodyLabel("<span style='font-size: 15px;'>已启用隐私保护</span>")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet("color: black;")
        hint_desc.setStyleSheet(f"color: {TEXT_MUTED};")

        layout.addLayout(icon_container)
        layout.addSpacing(12)
        layout.addWidget(hint_label)
        layout.addWidget(hint_desc)
        layout.addSpacing(18)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    mask = PrivacyMask()
    mask.move(868, 381)
    mask.resize(440, 386)
    mask.show()
    app.exec()
