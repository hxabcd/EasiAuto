from __future__ import annotations

import sys
from abc import abstractmethod

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon, IconWidget, ImageLabel, IndeterminateProgressRing, PrimaryPushButton

from EasiAuto.core.utils import QABCMeta, get_resource, get_scale, get_screen_size
from EasiAuto.view.tokens import (
    BRAND,
    OVERLAY_BOTTOM_BG,
    OVERLAY_CARD_BG,
    OVERLAY_SHADOW,
    OVERLAY_TEXT,
    OVERLAY_TEXT_DIM,
    RADIUS_OVERLAY,
)


class StatusOverlayBase(QWidget, metaclass=QABCMeta):
    """状态浮窗基类"""

    stop_clicked = Signal()

    def __init__(
        self, task_text: str = "正在运行", progress_text: str = "等待同步状态...", parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(440)

        self.finished_icon = IconWidget(FluentIcon.COMPLETED.colored(QColor(OVERLAY_TEXT), QColor(OVERLAY_TEXT)))
        self.failed_icon = IconWidget(FluentIcon.INFO.colored(QColor(OVERLAY_TEXT), QColor(OVERLAY_TEXT)))

        if parent is None:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
            )
        else:
            parent.installEventFilter(self)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 阴影容器
        shadow_container = QWidget(self)
        shadow_container_layout = QVBoxLayout(shadow_container)
        shadow_container_layout.setContentsMargins(10, 10, 10, 10)
        shadow_container_layout.setSpacing(0)

        self.card = self._init_main_card(task_text, progress_text)

        shadow_container_layout.addWidget(self.card)
        outer_layout.addWidget(shadow_container)

        self.stop_button_wrapper.clicked.connect(self.stop_clicked.emit)
        self.stop_button_wrapper.clicked.connect(self.on_stop_clicked)
        self._reposition()

    @abstractmethod
    def _init_main_card(self, task_text: str, progress_text: str) -> QWidget:
        """界面初始化"""

    def _reposition(self):
        w, h = get_screen_size()
        scale = get_scale()

        x = (w - self.width()) // 2
        y = h - int(54 / scale) - self.height()

        self.move(x, y)

    def showEvent(self, event):
        self._reposition()
        return super().showEvent(event)

    @property
    @abstractmethod
    def stop_button_wrapper(self) -> QPushButton: ...

    @property
    @abstractmethod
    def task_label_wrapper(self) -> QLabel: ...

    @property
    @abstractmethod
    def progress_label_wrapper(self) -> QLabel: ...

    @property
    @abstractmethod
    def status_badge_wrapper(self) -> QStackedWidget: ...

    def set_task_text(self, text: str):
        """更新状态文本"""
        self.task_label_wrapper.setText(text)

    def set_progress_text(self, text: str):
        """更新进度文本"""
        self.progress_label_wrapper.setText(text)

    def on_stop_clicked(self):
        self.set_task_text("正在取消登录")
        self.set_progress_text("稍等片刻……")
        self.stop_button_wrapper.setDisabled(True)

    def on_success(self):
        """成功时显示的提示"""
        self.set_task_text("自动登录成功")
        self.set_progress_text("登录任务已成功完成")
        self.status_badge_wrapper.setCurrentWidget(self.finished_icon)
        self.stop_button_wrapper.hide()

    def on_interrupted(self):
        """中断时显示的提示"""
        self.set_task_text("已取消")
        self.set_progress_text("登录任务已被取消")
        self.status_badge_wrapper.setCurrentWidget(self.failed_icon)
        self.stop_button_wrapper.hide()

    def on_failed(self):
        """失败时显示的提示"""
        self.task_label_wrapper.setText("自动登录失败")
        self.progress_label_wrapper.setText("检查日志以获取详细信息")
        self.status_badge_wrapper.setCurrentWidget(self.failed_icon)
        self.stop_button_wrapper.hide()


class StatusOverlay(StatusOverlayBase):
    """完整的状态浮窗"""

    def _init_main_card(self, task_text: str, progress_text: str, parent: QWidget | None = None):
        card = QFrame()
        card.setObjectName("statusCardOverlayCard")
        card.setStyleSheet(f"QFrame#statusCardOverlayCard {{background-color: {OVERLAY_CARD_BG};border-radius: {RADIUS_OVERLAY}px;}}")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(16)
        shadow.setOffset(2, 4)
        shadow.setColor(QColor(OVERLAY_SHADOW))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # 顶部状态区
        top = QWidget(card)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(32, 26, 32, 26)
        top_layout.setSpacing(20)

        self.status_badge = QStackedWidget()
        self.status_badge.setFixedSize(64, 64)

        self.progress_ring = IndeterminateProgressRing(self.status_badge)
        self.progress_ring.setFixedSize(64, 64)
        self.progress_ring.start()

        self.status_badge.addWidget(self.progress_ring)
        self.status_badge.addWidget(self.finished_icon)
        self.status_badge.addWidget(self.failed_icon)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(8)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.task_label = QLabel(task_text, top)
        title_font = QFont("Microsoft YaHei UI", 24, QFont.Weight.Bold)
        self.task_label.setFont(title_font)
        self.task_label.setStyleSheet(f"color: {OVERLAY_TEXT};")

        self.progress_label = QLabel(progress_text, top)
        progress_font = QFont("Microsoft YaHei UI", 14, QFont.Weight.Normal)
        self.progress_label.setFont(progress_font)
        self.progress_label.setStyleSheet(f"color: {OVERLAY_TEXT_DIM};")

        text_layout.addWidget(self.task_label)
        text_layout.addWidget(self.progress_label)

        top_layout.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        top_layout.addLayout(text_layout)
        top_layout.addStretch(1)

        # 底部操作条
        self.bottom = QFrame(card)
        self.bottom.setObjectName("statusCardOverlayBottom")
        self.bottom.setFixedHeight(72)
        self.bottom.setStyleSheet(f"""
            QFrame#statusCardOverlayBottom {{
                background-color: {OVERLAY_BOTTOM_BG};
                border-bottom-left-radius: {RADIUS_OVERLAY}px;
                border-bottom-right-radius: {RADIUS_OVERLAY}px;
            }}
        """)

        bottom_layout = QHBoxLayout(self.bottom)
        bottom_layout.setContentsMargins(32, 0, 32, 0)
        bottom_layout.setSpacing(8)

        self.logo = ImageLabel(self.bottom)
        self.logo.setImage(get_resource("icons/EasiAuto.ico"))
        self.logo.setFixedSize(32, 32)
        self.logo.setScaledContents(True)

        self.brand_label = QLabel("EasiAuto", self.bottom)
        brand_font = QFont("Microsoft YaHei UI", 18, QFont.Weight.Bold)
        self.brand_label.setFont(brand_font)
        self.brand_label.setStyleSheet(f"color: {OVERLAY_TEXT};")

        self.stop_button = PrimaryPushButton("停止", icon=FluentIcon.CANCEL_MEDIUM)
        self.stop_button.setFixedSize(100, 36)

        bottom_layout.addWidget(self.logo)
        bottom_layout.addWidget(self.brand_label)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.stop_button)

        card_layout.addWidget(top)
        card_layout.addWidget(self.bottom)

        return card

    @property
    def stop_button_wrapper(self) -> QPushButton:
        return self.stop_button

    @property
    def task_label_wrapper(self) -> QLabel:
        return self.task_label

    @property
    def progress_label_wrapper(self) -> QLabel:
        return self.progress_label

    @property
    def status_badge_wrapper(self) -> QStackedWidget:
        return self.status_badge


class SmallStatusOverlay(StatusOverlayBase):
    """另一个体积更小的状态浮窗"""

    def _init_main_card(self, task_text: str, progress_text: str, parent: QWidget | None = None):
        card = QFrame()
        card.setObjectName("statusCardOverlayCard")
        card.setStyleSheet(f"QFrame#statusCardOverlayCard {{background-color: {OVERLAY_CARD_BG};border-radius: {RADIUS_OVERLAY}px;}}")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(16)
        shadow.setOffset(2, 4)
        shadow.setColor(QColor(OVERLAY_SHADOW))
        card.setGraphicsEffect(shadow)

        card_layout = QHBoxLayout(card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        card_layout.setContentsMargins(24, 18, 24, 18)
        card_layout.setSpacing(20)

        self.status_badge = QStackedWidget()
        self.status_badge.setFixedSize(48, 48)

        self.progress_ring = IndeterminateProgressRing(self.status_badge)
        self.progress_ring.setFixedSize(48, 48)
        self.progress_ring.start()

        self.status_badge.addWidget(self.progress_ring)
        self.status_badge.addWidget(self.finished_icon)
        self.status_badge.addWidget(self.failed_icon)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(8)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.task_label = QLabel(task_text)
        title_font = QFont("Microsoft YaHei UI", 16, QFont.Weight.Bold)
        self.task_label.setFont(title_font)
        self.task_label.setStyleSheet(f"color: {OVERLAY_TEXT};")

        self.progress_label = QLabel(progress_text)
        progress_font = QFont("Microsoft YaHei UI", 12, QFont.Weight.Normal)
        self.progress_label.setFont(progress_font)
        self.progress_label.setStyleSheet(f"color: {OVERLAY_TEXT_DIM};")

        text_layout.addWidget(self.task_label)
        text_layout.addWidget(self.progress_label)

        self.stop_button = PrimaryPushButton("停止", icon=FluentIcon.CANCEL_MEDIUM)
        self.stop_button.setFixedSize(100, 36)

        card_layout.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(text_layout)
        card_layout.addStretch(1)
        card_layout.addWidget(self.stop_button)

        return card

    @property
    def stop_button_wrapper(self) -> QPushButton:
        return self.stop_button

    @property
    def task_label_wrapper(self) -> QLabel:
        return self.task_label

    @property
    def progress_label_wrapper(self) -> QLabel:
        return self.progress_label

    @property
    def status_badge_wrapper(self) -> QStackedWidget:
        return self.status_badge


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme, setThemeColor

    app = QApplication(sys.argv)

    setTheme(Theme.DARK)
    setThemeColor(BRAND)
    overlay = StatusOverlay()
    overlay.logo.setImage("d:/MyPC/Dev/Projects/EasiAuto/resources/icons/EasiAuto.ico")
    overlay.logo.setFixedSize(32, 32)
    overlay.logo.setScaledContents(True)
    overlay.show()
    overlay.stop_clicked.connect(app.exit)
    sys.exit(app.exec())
