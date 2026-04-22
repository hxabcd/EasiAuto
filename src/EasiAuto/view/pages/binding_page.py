from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QScroller, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    AvatarWidget,
    BodyLabel,
    CardWidget,
    CommandBar,
    FluentIcon,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    SmoothScrollArea,
    SubtitleLabel,
    VerticalSeparator,
)

from EasiAuto.common.profile import EasiAutomation, SubjectRef, profile
from EasiAuto.core.binding_sync import ClassIslandBindingBackend
from EasiAuto.view.utils import get_main_container


@dataclass
class _SubjectRow:
    subject: SubjectRef
    automation_id: str | None
    original_index: int


class SubjectCard(CardWidget):
    subjectClicked = Signal(str)

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._selected = False

        self.setMinimumHeight(60)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.subject_label = SubtitleLabel("")
        self.status_label = BodyLabel("")
        self.status_label.setWordWrap(True)

        layout.addWidget(self.subject_label)
        layout.addStretch(1)
        layout.addWidget(self.status_label)

        self._apply_selected_style()

    def set_content(self, subject_name: str, status_text: str):
        self.subject_label.setText(subject_name)
        self.status_label.setText(status_text)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_selected_style()

    def _apply_selected_style(self):
        if self._selected:
            self.setStyleSheet("CardWidget { border: 1px solid rgba(0, 200, 132, 0.85); border-radius: 8px; }")
        else:
            self.setStyleSheet("CardWidget { border: 1px solid rgba(120, 120, 120, 0); border-radius: 8px; }")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.subjectClicked.emit(self.key)
        super().mousePressEvent(e)

    # def resizeEvent(self, event):
    #     target = max(100, int(self.width() * 2 / 3))
    #     if abs(self.height() - target) > 1:
    #         self.setFixedHeight(target)
    #     super().resizeEvent(event)


class UnboundCard(CardWidget):
    """未绑定卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # 左侧图标（比头像略小）
        self.icon_label = IconWidget(FluentIcon.UNPIN)
        self.icon_label.setFixedSize(24, 24)

        # 中间文字
        self.name_label = SubtitleLabel("未绑定")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.name_label)
        layout.addStretch(1)

    def set_checked(self, checked: bool):
        if checked:
            self.setStyleSheet("CardWidget { border: 1px solid rgba(0, 200, 132, 0.85); border-radius: 8px; }")
        else:
            self.setStyleSheet("CardWidget { border: 1px solid rgba(120, 120, 120, 0); border-radius: 8px; }")


class ProfileCard(CardWidget):
    """档案卡片"""

    editClicked = Signal(str)  # profile_id

    def __init__(self, profile_id: str | None, display_name: str, account_name: str, parent=None):
        super().__init__(parent)
        self.profile_id = profile_id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # 左侧头像
        self.avatar_label = AvatarWidget()
        self.avatar_label.setRadius(32)
        if profile_id:
            self.avatar_label.setText(display_name[:1])

        # 中间信息
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self.name_label = SubtitleLabel(display_name)
        self.account_label = BodyLabel(account_name)

        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.account_label)

        # 右侧编辑按钮
        self.command_bar = CommandBar()
        self.command_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.action_edit = Action(
            FluentIcon.EDIT,
            "编辑",
            triggered=lambda: self.editClicked.emit(profile_id) if profile_id else None,
        )
        self.command_bar.addAction(self.action_edit)

        layout.addWidget(self.avatar_label)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self.command_bar, alignment=Qt.AlignmentFlag.AlignRight)

    def set_checked(self, checked: bool):
        if checked:
            self.setStyleSheet("CardWidget { border: 1px solid rgba(0, 200, 132, 0.85); border-radius: 8px; }")
        else:
            self.setStyleSheet("CardWidget { border: 1px solid rgba(120, 120, 120, 0); border-radius: 8px; }")


class BindingPage(QWidget):
    # TODO: 优化后端事件绑定
    bindingsChanged = Signal()
    editClicked = Signal(str)  # automation_id
    provider = "classisland"

    def __init__(self):
        super().__init__()
        self.setObjectName("BindingPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        self.backend = ClassIslandBindingBackend()
        self.subject_rows: dict[str, _SubjectRow] = {}
        self.subject_cards: dict[str, SubjectCard] = {}
        self.subject_divider: QWidget | None = None
        self.profile_cards: dict[str | None, ProfileCard | UnboundCard] = {}
        self.current_subject_key: str | None = None
        self.preferred_profile_id: str | None = None
        self._updating_cards = False

        self._init_ui()
        self.reload()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        main = QWidget()
        main_layout = QHBoxLayout(main)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        subject_header = QWidget()
        subject_header_layout = QHBoxLayout(subject_header)
        subject_header_layout.setContentsMargins(8, 0, 8, 0)
        subject_header_layout.setSpacing(6)
        subject_header_layout.addWidget(SubtitleLabel("科目"))
        subject_header_layout.addStretch(1)

        self.subject_action_bar = CommandBar()
        self.subject_action_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.action_clear_bindings = Action(
            FluentIcon.CANCEL_MEDIUM, "清空绑定", triggered=self._on_clear_bindings_clicked
        )
        self.subject_action_bar.addAction(self.action_clear_bindings)
        subject_header_layout.addWidget(self.subject_action_bar, alignment=Qt.AlignmentFlag.AlignRight)

        left_layout.addWidget(subject_header)

        self.subject_scroll = SmoothScrollArea()
        self.subject_scroll.setWidgetResizable(True)
        self.subject_scroll.setFrameShape(SmoothScrollArea.Shape.NoFrame)
        self.subject_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        QScroller.grabGesture(self.subject_scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.subject_container = QWidget()
        self.subject_grid = QGridLayout(self.subject_container)
        self.subject_grid.setContentsMargins(0, 0, 16, 0)
        self.subject_grid.setHorizontalSpacing(8)
        self.subject_grid.setVerticalSpacing(8)
        self.subject_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.subject_scroll.setWidget(self.subject_container)
        left_layout.addWidget(self.subject_scroll, 1)

        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(8, 0, 8, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(SubtitleLabel("档案"))

        self.profile_scroll = SmoothScrollArea()
        self.profile_scroll.setWidgetResizable(True)
        self.profile_scroll.setFrameShape(SmoothScrollArea.Shape.NoFrame)
        self.profile_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        QScroller.grabGesture(self.profile_scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.profile_container = QWidget()
        self.profile_layout = QVBoxLayout(self.profile_container)
        self.profile_layout.setContentsMargins(0, 0, 0, 0)
        self.profile_layout.setSpacing(6)
        self.profile_scroll.setWidget(self.profile_container)
        right_layout.addWidget(self.profile_scroll, 1)

        main_layout.addWidget(self.left_panel, 1)
        main_layout.addWidget(VerticalSeparator())
        main_layout.addWidget(self.right_panel, 1)

        layout.addWidget(main)

    @staticmethod
    def _subject_key(subject: SubjectRef) -> str:
        if subject.id:
            return f"{subject.provider}:{subject.id}"
        return f"{subject.provider}:name:{subject.name.strip().lower()}"

    @staticmethod
    def _binding_keys(subject_ref: SubjectRef) -> list[str]:
        keys = [f"{subject_ref.provider}:name:{subject_ref.name.strip().lower()}"]
        if subject_ref.id:
            keys.insert(0, f"{subject_ref.provider}:{subject_ref.id}")
        return keys

    @staticmethod
    def _profile_display_name(automation: EasiAutomation) -> str:
        label = automation.display_name or "未命名档案"
        if not automation.enabled:
            label = f"{label} (禁用)"
        return label

    def _subject_status_text(self, row: _SubjectRow) -> str:
        if not row.automation_id:
            return "未绑定"
        auto = profile.get_automation(row.automation_id)
        if not auto:
            return "绑定已失效"
        return f"绑定到：{self._profile_display_name(auto)}"

    def _clear_subject_grid(self):
        while self.subject_grid.count():
            item = self.subject_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _clear_profile_cards(self):
        while self.profile_layout.count():
            item = self.profile_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _build_subject_cards(self):
        # 复用卡片，仅重排位置，减少销毁/重建造成的抽搐
        self.subject_container.setUpdatesEnabled(False)
        try:
            ordered_rows = self._ordered_subject_rows()
            bound_rows = [(key, row) for key, row in ordered_rows if row.automation_id is not None]
            unbound_rows = [(key, row) for key, row in ordered_rows if row.automation_id is None]

            # 删除已不存在的科目卡片
            removed_keys = [key for key in self.subject_cards if key not in self.subject_rows]
            for key in removed_keys:
                card = self.subject_cards.pop(key)
                card.deleteLater()

            # 创建缺失卡片并更新内容
            for key, row in ordered_rows:
                card = self.subject_cards.get(key)
                if card is None:
                    card = SubjectCard(key, self.subject_container)
                    card.subjectClicked.connect(self._on_subject_selected)
                    self.subject_cards[key] = card
                card.set_content(row.subject.name, self._subject_status_text(row))

            # 清空布局位置，但不销毁复用控件
            while self.subject_grid.count():
                item = self.subject_grid.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.hide()

            if self.subject_divider is None:
                self.subject_divider = self._build_subject_divider()

            current_grid_row = 0
            for i, (key, row) in enumerate(bound_rows):
                card = self.subject_cards[key]
                self.subject_grid.addWidget(card, current_grid_row + i // 2, i % 2)
                card.show()

            if bound_rows:
                current_grid_row += (len(bound_rows) + 1) // 2

            if bound_rows and unbound_rows:
                self.subject_divider.show()
                self.subject_grid.addWidget(self.subject_divider, current_grid_row, 0, 1, 2)
            else:
                self.subject_divider.hide()

            if bound_rows and unbound_rows:
                current_grid_row += 1

            for i, (key, row) in enumerate(unbound_rows):
                card = self.subject_cards[key]
                self.subject_grid.addWidget(card, current_grid_row + i // 2, i % 2)
                card.show()

            if unbound_rows:
                current_grid_row += (len(unbound_rows) + 1) // 2
        finally:
            self.subject_container.setUpdatesEnabled(True)
            self.subject_container.update()

    def _build_subject_divider(self) -> QWidget:
        divider = QWidget(self.subject_container)
        layout = QHBoxLayout(divider)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        left_line = QFrame()
        left_line.setFrameShape(QFrame.Shape.HLine)
        left_line.setFrameShadow(QFrame.Shadow.Plain)
        left_line.setStyleSheet("color: rgba(120, 120, 120, 80);")

        right_line = QFrame()
        right_line.setFrameShape(QFrame.Shape.HLine)
        right_line.setFrameShadow(QFrame.Shadow.Plain)
        right_line.setStyleSheet("color: rgba(120, 120, 120, 80);")

        label = BodyLabel("未绑定")
        label.setStyleSheet("color: rgba(120, 120, 120, 180);")

        layout.addWidget(left_line, 1)
        layout.addWidget(label)
        layout.addWidget(right_line, 1)
        return divider

    def _build_profile_cards(self):
        self._clear_profile_cards()
        self.profile_cards.clear()

        # 未绑定卡片
        card_unbound = UnboundCard()
        card_unbound.clicked.connect(lambda: self._on_profile_card_clicked(None))
        self.profile_cards[None] = card_unbound
        self.profile_layout.addWidget(card_unbound)

        # 档案卡片
        for automation in profile.list_automations():
            display_name = self._profile_display_name(automation)
            account_name = automation.account_name or automation.account or ""
            card = ProfileCard(automation.id, display_name, account_name)
            card.clicked.connect(lambda pid=automation.id: self._on_profile_card_clicked(pid))
            card.editClicked.connect(self.editClicked)
            self.profile_cards[automation.id] = card
            self.profile_layout.addWidget(card)

        self.profile_layout.addStretch(1)

    def _set_card_selection(self, profile_id: str | None):
        self._updating_cards = True
        target_found = False
        for pid, card in self.profile_cards.items():
            matched = pid == profile_id
            card.set_checked(matched)
            if matched:
                target_found = True
        if not target_found and None in self.profile_cards:
            self.profile_cards[None].set_checked(True)
        self._updating_cards = False

    def _on_subject_selected(self, subject_key: str):
        self.current_subject_key = subject_key
        for key, card in self.subject_cards.items():
            card.set_selected(key == subject_key)

        row = self.subject_rows.get(subject_key)
        if row is None:
            self._set_card_selection(None)
            return

        current_profile_id = row.automation_id
        if current_profile_id is None and self.preferred_profile_id is not None:
            current_profile_id = self.preferred_profile_id
        self._set_card_selection(current_profile_id)

    def _on_profile_card_clicked(self, profile_id: str | None):
        if self._updating_cards or not self.current_subject_key:
            return

        row = self.subject_rows.get(self.current_subject_key)
        if row is None:
            return

        if row.automation_id == profile_id:
            return

        row.automation_id = profile_id

        current_subject_key = self.current_subject_key
        self._build_subject_cards()
        if current_subject_key:
            self._on_subject_selected(current_subject_key)

        self._set_card_selection(profile_id)
        self._persist_and_sync()

    def _ordered_subject_rows(self) -> list[tuple[str, _SubjectRow]]:
        return sorted(
            self.subject_rows.items(),
            key=lambda item: (
                item[1].automation_id is None,
                item[1].original_index,
            ),
        )

    def _on_clear_bindings_clicked(self):
        changed = False
        for row in self.subject_rows.values():
            if row.automation_id is not None:
                row.automation_id = None
                changed = True

        if not changed:
            return

        current_subject_key = self.current_subject_key
        self._build_subject_cards()
        if current_subject_key:
            self._on_subject_selected(current_subject_key)

        self._set_card_selection(None)
        self._persist_and_sync()

    def reload(self, reload: bool = False):
        previous_subject_key = self.current_subject_key

        logger.debug("刷新关联页数据")
        self.subject_rows.clear()
        self.current_subject_key = None

        subjects = self.backend.list_subjects(reload=reload)
        for i, subject in enumerate(subjects):
            key = self._subject_key(subject)
            automation_id = profile.get_automation_id_by_subject(subject)
            self.subject_rows[key] = _SubjectRow(
                subject=subject,
                automation_id=automation_id,
                original_index=i,
            )

        self._build_subject_cards()
        self._build_profile_cards()

        if self.subject_rows:
            ordered_rows = self._ordered_subject_rows()
            target_key = previous_subject_key if previous_subject_key in self.subject_rows else ordered_rows[0][0]
            self._on_subject_selected(target_key)

    def open_with_profile(self, profile_id: str):
        self.preferred_profile_id = profile_id
        self.reload(reload=True)

    def _persist_and_sync(self):
        old_guid_lookup: dict[str, str | None] = {}
        for binding in profile.list_bindings():
            for key in self._binding_keys(binding.subject):
                old_guid_lookup[key] = binding.id

        profile.clear_bindings()
        for key, row in self._ordered_subject_rows():
            if not row.automation_id:
                continue
            profile.set_binding(
                subject=row.subject,
                automation_id=row.automation_id,
                id=old_guid_lookup.get(key),
            )

        profile.save(reason="bindings_local_updated")

        ok = self.backend.sync(profile)
        profile.save(reason="bindings_changed")

        if not ok:
            errors = self.backend.last_errors
            content = "；".join(errors[:3]) if errors else "请检查 ClassIsland 状态与配置"
            if len(errors) > 3:
                content += "；..."
            InfoBar.error(
                title="同步存在失败项",
                content=content,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=get_main_container(),
            )

        self.bindingsChanged.emit()
