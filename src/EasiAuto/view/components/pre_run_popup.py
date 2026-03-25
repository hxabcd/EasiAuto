from enum import Enum
from typing import Any

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
)
from qfluentwidgets import (
    Dialog,
    FluentIcon,
    ImageLabel,
    PrimaryPushButton,
    PushButton,
)

from EasiAuto.common.utils import get_resource


class DialogResponse(Enum):
    CANCEL = 0
    CONTINUE = 1
    TIMEOUT = 2
    DELAY = 3


class PreRunPopup(Dialog):
    """运行前的确认弹窗"""

    recievedResponse = Signal(DialogResponse)

    def __init__(self):
        super().__init__(title="EasiAuto", content="将在 N/A 秒后继续执行")
        self.setWindowIcon(QIcon(get_resource("EasiAuto.ico")))

        self.response: DialogResponse | None = None

        self.is_dragging = False
        self.drag_position = QPoint()
        self.title_bar_height = 30

        # 文本
        self.iconLabel = ImageLabel()
        self.iconLabel.setImage(get_resource("EasiAuto.ico"))
        self.iconLabel.setScaledContents(True)
        self.iconLabel.setFixedSize(50, 50)

        self.title_layout = QHBoxLayout()
        self.titleLabel.setText("即将运行希沃白板自动登录")
        self.titleLabel.setStyleSheet("font-size: 25px; font-weight: bold;")

        self.contentLabel.setStyleSheet("font-size: 16px;")

        self.title_layout.setSpacing(12)
        self.title_layout.addWidget(self.iconLabel)
        self.title_layout.addWidget(self.titleLabel)

        self.textLayout.insertLayout(0, self.title_layout)

        # 按钮
        self.yesButton.hide()
        self.cancelButton.hide()

        self.cancel_btn = PushButton(FluentIcon.CANCEL_MEDIUM, "取消")
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.clicked.connect(lambda: self.respond(DialogResponse.CANCEL))

        self.delay_btn = PushButton(FluentIcon.PAUSE, "推迟")
        self.delay_btn.setFixedWidth(100)
        self.delay_btn.clicked.connect(lambda: self.respond(DialogResponse.DELAY))

        self.execute_btn = PrimaryPushButton(FluentIcon.ACCEPT_MEDIUM, "立即执行")
        self.execute_btn.setFixedWidth(150)
        self.execute_btn.clicked.connect(lambda: self.respond(DialogResponse.CONTINUE))

        self.buttonLayout.insertWidget(0, self.cancel_btn)
        self.buttonLayout.insertWidget(1, self.delay_btn)
        self.buttonLayout.insertStretch(2, 1)
        self.buttonLayout.insertWidget(3, self.execute_btn)

        # 快捷键绑定
        self.execute_btn.setDefault(True)
        self.execute_btn.setFocus()
        self.cancel_btn.setAutoDefault(False)
        self.delay_btn.setAutoDefault(False)

        self.execute_btn.setShortcut("Return")
        self.execute_btn.setShortcut("Enter")
        self.cancel_btn.setShortcut("Esc")
        self.delay_btn.setShortcut("Ctrl+P")

    def exec(self) -> int:
        self.setStayOnTop(True)  # NOTE:  必须在显示时才能设置置顶，否则窗口显示位置不会居中
        return super().exec()

    def respond(self, result: DialogResponse) -> None:
        self.close()
        self.response = result
        self.recievedResponse.emit(result)

    def countdown(self, timeout: int) -> DialogResponse:
        self.response = DialogResponse.CANCEL

        if timeout <= 0:
            raise ValueError("倒计时时长必须是正整数")

        # 更新倒计时文本
        def update_text():
            nonlocal timeout
            if timeout > 0:
                self.contentLabel.setText(
                    "<span style='color: transparent;'>占位文本</span>"
                    + f"将在 <span style='font-size: 20px; font-weight: 600; font-family: monospace;'>{timeout}</span> 秒后继续执行"
                )
                timeout -= 1
            else:
                self.respond(DialogResponse.TIMEOUT)

        update_text()

        # 计时器
        timer = QTimer()
        timer.timeout.connect(update_text)
        timer.setInterval(1000)
        timer.start()

        self.exec()

        timer.stop()
        return self.response

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.y() <= self.title_bar_height:
            self.is_dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: Any) -> None:
        if self.is_dragging:
            self.move(event.globalPos() - self.drag_position)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
