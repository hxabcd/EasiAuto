from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    HyperlinkButton,
    InfoBarIcon,
    SimpleCardWidget,
    StrongBodyLabel,
    TransparentToolButton,
    drawIcon,
    isDarkTheme,
)

from EasiAuto.services.announcement_service import Announcement
from EasiAuto.view.helpers import set_tooltip
from EasiAuto.view.tokens import (
    BRAND,
    RADIUS_SETTING,
    SEVERITY_ERROR_ACCENT,
    SEVERITY_ERROR_BG_DARK,
    SEVERITY_ERROR_BG_LIGHT,
    SEVERITY_WARNING_ACCENT,
    SEVERITY_WARNING_BG_DARK,
    SEVERITY_WARNING_BG_LIGHT,
)


class SeverityIcon(QWidget):
    """InfoBarIcon 圆形按严重性着色，保留白色字形"""

    def __init__(self, icon: InfoBarIcon, accent: str, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.accent = accent
        self.setFixedSize(18, 18)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        # 只给第 0 个 path（圆形）上色，字形保持白色（同 InfoBar 的 InfoIconWidget）
        drawIcon(self.icon, painter, QRectF(self.rect()), indexes=[0], fill=QColor(self.accent).name())


class AnnouncementCard(SimpleCardWidget):
    """设置页公告卡片（Fluent 风格）"""

    def __init__(self, announcement: Announcement, on_close: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.announcement = announcement
        self._on_close = on_close

        self.setObjectName(f"AnnouncementCard_{announcement.id}")
        self.setBorderRadius(RADIUS_SETTING)

        # 严重性背景着色（同 InfoBar 原版）
        self._light_bg, self._dark_bg = self._resolve_background(announcement.severity)
        self.setBackgroundColor(self._normalBackgroundColor())

        # 左侧严重性图标（圆形着色，与标题对齐）
        self.icon_label = SeverityIcon(
            self._resolve_icon(announcement.severity),
            self._resolve_accent_color(announcement.severity),
            self,
        )

        # 标题 + 正文
        self.title_label = StrongBodyLabel(announcement.title, self)
        self.content_label = BodyLabel(announcement.content, self)
        self.content_label.setWordWrap(True)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.content_label)

        # 查看详情
        self.link_button: HyperlinkButton | None = None
        if announcement.link:
            self.link_button = HyperlinkButton(FluentIcon.LINK, announcement.link, "详情", self)
            set_tooltip(self.link_button, announcement.link)

        # 忽略公告
        self.close_button = TransparentToolButton(FluentIcon.CLOSE, self)
        self.close_button.clicked.connect(self._handle_close)
        set_tooltip(self.close_button, "忽略此公告")

        # 统一两个操作按钮的高度，保证内容垂直对齐
        height = self.close_button.sizeHint().height()
        if self.link_button:
            height = max(height, self.link_button.sizeHint().height())
            self.link_button.setFixedHeight(height)
        self.close_button.setFixedHeight(height)

        # 水平布局：图标 | 文字 | 操作
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, 1)
        if self.link_button:
            layout.addWidget(self.link_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)

    def _handle_close(self) -> None:
        self._on_close(self.announcement.id)

    def _normalBackgroundColor(self):
        if getattr(self, "_light_bg", None) is None:
            return super()._normalBackgroundColor()
        return QColor(self._dark_bg if isDarkTheme() else self._light_bg)

    def _hoverBackgroundColor(self):
        return self._normalBackgroundColor() if getattr(self, "_light_bg", None) else super()._hoverBackgroundColor()

    def _pressedBackgroundColor(self):
        return self._normalBackgroundColor() if getattr(self, "_light_bg", None) else super()._pressedBackgroundColor()

    @staticmethod
    def _resolve_icon(severity: str) -> InfoBarIcon:
        if severity == "warning":
            return InfoBarIcon.WARNING
        if severity == "error":
            return InfoBarIcon.ERROR
        return InfoBarIcon.INFORMATION

    @staticmethod
    def _resolve_background(severity: str) -> tuple[str | None, str | None]:
        if severity == "warning":
            return SEVERITY_WARNING_BG_LIGHT, SEVERITY_WARNING_BG_DARK
        if severity == "error":
            return SEVERITY_ERROR_BG_LIGHT, SEVERITY_ERROR_BG_DARK
        return None, None

    @staticmethod
    def _resolve_accent_color(severity: str) -> str:
        if severity == "warning":
            return SEVERITY_WARNING_ACCENT
        if severity == "error":
            return SEVERITY_ERROR_ACCENT
        return BRAND
