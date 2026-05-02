from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget
from qfluentwidgets import InfoBar, InfoBarIcon, InfoBarPosition, PushButton, TextWrap

from EasiAuto.services.announcement_service import Announcement


class AnnouncementCard(InfoBar):
    def __init__(self, announcement: Announcement, on_close: Callable[[str], None], parent: QWidget | None = None):
        self.announcement = announcement
        self._on_close = on_close

        super().__init__(
            icon=self._resolve_icon(announcement.severity),
            title=announcement.title,
            content=announcement.content,
            orient=Qt.Orientation.Vertical,
            isClosable=True,
            position=InfoBarPosition.NONE,
            duration=-1,
            parent=parent,
        )

        self.setObjectName(f"AnnouncementCard_{announcement.id}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.closedSignal.connect(self._handle_close)

        light_bg, dark_bg = self._resolve_background(announcement.severity)
        if light_bg and dark_bg:
            self.setCustomBackgroundColor(light_bg, dark_bg)

        self.hBoxLayout.setSizeConstraint(self.hBoxLayout.SizeConstraint.SetDefaultConstraint)
        self.hBoxLayout.setStretch(1, 1)

        self.titleLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.contentLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.titleLabel.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.contentLabel.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        if announcement.link:
            detail_button = PushButton("查看详情", self)
            detail_button.clicked.connect(self._open_link)
            self.addWidget(detail_button)

    def _adjustText(self):
        w = 900 if not self.parent() else (self.parent().width())  # type: ignore

        # adjust title
        chars = int(max(min(w / 10, 120), 30))
        self.titleLabel.setText(TextWrap.wrap(self.title, chars, False)[0])

        # adjust content
        chars = int(max(min(w / 9, 120), 30))
        self.contentLabel.setText(TextWrap.wrap(self.content, chars, False)[0])

    def _limit_content_lines(self, max_lines: int) -> None:
        self.contentLabel.setMaximumHeight(self._line_limit_height(self.contentLabel, max_lines))

    @staticmethod
    def _line_limit_height(label: QLabel, max_lines: int) -> int:
        metrics = label.fontMetrics()
        return metrics.lineSpacing() * max_lines + 2

    def _open_link(self) -> None:
        if self.announcement.link:
            QDesktopServices.openUrl(QUrl(self.announcement.link))

    def _handle_close(self) -> None:
        self._on_close(self.announcement.id)

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
            return "#fff4ce", "#5c4500"
        if severity == "error":
            return "#fde7e9", "#442726"
        return None, None

    @staticmethod
    def _resolve_accent_color(severity: str) -> str:
        if severity == "warning":
            return "#ffb900"
        if severity == "error":
            return "#a4262c"
        return "#00C884"
