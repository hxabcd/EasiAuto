"""档案列表卡片组件"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    AvatarWidget,
    BodyLabel,
    CardWidget,
    CommandBar,
    FluentIcon,
    HorizontalSeparator,
    SubtitleLabel,
    SwitchButton,
)

from EasiAuto.models.profile import BaseAutomation, profile

from ..helpers import get_main_window
from .qfw_widgets import PillOverflowBar, PillPushButton


class ProfileCard(CardWidget):
    """档案卡片"""

    itemClicked = Signal(QListWidgetItem)
    actionRun = Signal(str)  # automation_id
    actionExport = Signal(str)  # automation_id
    actionRemove = Signal(QListWidgetItem)
    enabledChanged = Signal(str, bool)  # automation_id, enabled

    def __init__(self, item: QListWidgetItem, automation_id: str | None = None):
        super().__init__()
        self.list_item = item
        self._automation_id = automation_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 上半区域：头像 + 信息
        self.info_container = QWidget()
        info_layout = QHBoxLayout(self.info_container)
        info_layout.setContentsMargins(16, 16, 16, 16)
        info_layout.setSpacing(14)

        self.avatar_label = AvatarWidget()
        self.avatar_label.setRadius(32)
        if self.automation:
            if img := getattr(self.automation, "avatar", None):
                self.avatar_label.setImage(img)
            elif name := self.automation.display_name:
                self.avatar_label.setText(name[0].upper())
        else:
            self.avatar_label.setText("?")

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self.name_label = SubtitleLabel(self.automation.display_name or "未命名自动化")
        self.detail_label = BodyLabel(self.automation.detail_name)
        self.detail_label.setTextColor(QColor("#878787"), QColor("#b5b5b5"))

        self.subject_bar = PillOverflowBar()
        self.subject_bar.setContentsMargins(0, 6, 0, 0)
        self.subject_bar.setSpacing(6)

        self.add_subject_button = PillPushButton("添加", icon=FluentIcon.ADD)
        self.add_subject_button.clicked.connect(self._on_add_subject)
        self.subject_bar.setLastWidget(self.add_subject_button)

        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.detail_label)
        text_layout.addWidget(self.subject_bar)

        info_layout.addWidget(self.avatar_label)
        info_layout.addLayout(text_layout, 1)

        # 下半区域：动作栏
        self.action_container = QWidget()
        action_layout = QHBoxLayout(self.action_container)
        action_layout.setContentsMargins(12, 4, 12, 4)
        action_layout.setSpacing(0)

        self.command_bar = CommandBar()
        self.command_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.action_run = Action(
            FluentIcon.PLAY,
            "运行",
            triggered=self._on_run,
        )
        self.action_export = Action(
            FluentIcon.SHARE,
            "导出",
            triggered=self._on_export,
        )
        self.action_remove = Action(
            FluentIcon.CANCEL_MEDIUM,
            "删除",
            triggered=lambda: self.actionRemove.emit(self.list_item),
        )

        self.command_bar.addAction(self.action_run)
        self.command_bar.addAction(self.action_export)
        self.command_bar.addAction(self.action_remove)

        self.enabled_switch = SwitchButton()
        self.enabled_switch.setOnText("启用")
        self.enabled_switch.setOffText("禁用")
        self.enabled_switch.setChecked(self.automation.enabled if self.automation else False)
        self.enabled_switch.checkedChanged.connect(self._on_enabled_changed)

        action_layout.addWidget(self.command_bar, 1)
        action_layout.addWidget(self.enabled_switch, alignment=Qt.AlignmentFlag.AlignRight)
        action_layout.addSpacing(6)

        layout.addWidget(self.info_container)
        layout.addWidget(HorizontalSeparator())
        layout.addWidget(self.action_container)

        self.setMouseTracking(True)
        if self.automation:
            self.update_display(self.automation)

    @property
    def automation(self) -> BaseAutomation:
        if not self._automation_id:
            raise ValueError("未设置 automation_id")

        automation: BaseAutomation | None = self.list_item.data(Qt.ItemDataRole.UserRole)
        if automation and automation.id == self._automation_id:
            return automation

        if automation := profile.get_automation(self._automation_id):
            return automation

        raise ValueError(f"无法找到对应的自动化: {self._automation_id}")

    def _update_subjects(self, tags: list[str]):
        self.subject_bar.setTags(tags)

    def _on_add_subject(self):
        # TODO: 跳转至对应科目
        window = get_main_window()
        window.switchTo(window.automation_page)

    def _on_run(self):
        if self._automation_id:
            self.actionRun.emit(self._automation_id)

    def _on_export(self):
        if self._automation_id:
            self.actionExport.emit(self._automation_id)

    def update_display(self, automation: BaseAutomation):
        self._automation_id = automation.id
        self.name_label.setText(self.automation.display_name or "未命名自动化")
        self.detail_label.setText(self.automation.detail_name or "")
        self.enabled_switch.setChecked(automation.enabled)
        self.detail_label.setText(self.automation.detail_name or "")

        if img := getattr(self.automation, "avatar", None):
            try:
                self.avatar_label.setImage(str(img))
            except Exception:
                self.avatar_label.setText(self.automation.display_name[:1] if self.automation.display_name else "?")
        elif name := self.automation.display_name:
            self.avatar_label.setText(name[0].upper())
        else:
            self.avatar_label.setText("?")

    def set_subject_tags(self, tags: list[str]):
        self._update_subjects(tags)

    def _on_enabled_changed(self, enabled: bool):
        if self._automation_id:
            self.enabledChanged.emit(self._automation_id, enabled)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.itemClicked.emit(self.list_item)
        super().mousePressEvent(e)
