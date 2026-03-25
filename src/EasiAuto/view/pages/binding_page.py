from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QScroller, QVBoxLayout, QWidget
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

from EasiAuto.common.consts import PROFILE_PATH
from EasiAuto.common.profile import EasiAutomation, SubjectRef, profile
from EasiAuto.core.binding_sync import ClassIslandBindingBackend, SyncSubject
from EasiAuto.integrations.classisland_manager import classisland_manager as ci_manager
from EasiAuto.view.utils import get_main_container


@dataclass
class _SubjectRow:
    subject: SyncSubject
    profile_id: str | None


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
        left_layout.addWidget(SubtitleLabel("科目"))

        self.subject_scroll = SmoothScrollArea()
        self.subject_scroll.setWidgetResizable(True)
        self.subject_scroll.setFrameShape(SmoothScrollArea.Shape.NoFrame)
        self.subject_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        QScroller.grabGesture(self.subject_scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.subject_container = QWidget()
        self.subject_grid = QGridLayout(self.subject_container)
        self.subject_grid.setContentsMargins(0, 0, 0, 0)
        self.subject_grid.setHorizontalSpacing(8)
        self.subject_grid.setVerticalSpacing(8)
        self.subject_scroll.setWidget(self.subject_container)
        left_layout.addWidget(self.subject_scroll, 1)

        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
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
    def _subject_key(subject: SyncSubject) -> str:
        if subject.external_id:
            return f"{subject.provider}:{subject.external_id}"
        return f"{subject.provider}:name:{subject.name.strip().lower()}"

    @staticmethod
    def _binding_keys(subject_ref: SubjectRef) -> list[str]:
        keys = [f"{subject_ref.provider}:name:{subject_ref.name.strip().lower()}"]
        if subject_ref.external_id:
            keys.insert(0, f"{subject_ref.provider}:{subject_ref.external_id}")
        return keys

    @staticmethod
    def _profile_display_name(automation: EasiAutomation) -> str:
        label = automation.display_name or "未命名档案"
        if not automation.enabled:
            label = f"{label} (禁用)"
        return label

    def _subject_status_text(self, row: _SubjectRow) -> str:
        if not row.profile_id:
            return "未绑定"
        auto = profile.get_by_id(row.profile_id)
        if not auto:
            return "绑定已失效"
        return f"绑定: {self._profile_display_name(auto)}"

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
        self._clear_subject_grid()
        self.subject_cards.clear()

        for i, (key, row) in enumerate(self.subject_rows.items()):
            card = SubjectCard(key)
            card.set_content(row.subject.name, self._subject_status_text(row))
            card.subjectClicked.connect(self._on_subject_selected)
            self.subject_cards[key] = card
            self.subject_grid.addWidget(card, i // 2, i % 2)

        self.subject_grid.setRowStretch((len(self.subject_rows) + 1) // 2, 1)

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

        current_profile_id = row.profile_id
        if current_profile_id is None and self.preferred_profile_id is not None:
            current_profile_id = self.preferred_profile_id
        self._set_card_selection(current_profile_id)

    def _on_profile_card_clicked(self, profile_id: str | None):
        if self._updating_cards or not self.current_subject_key:
            return

        row = self.subject_rows.get(self.current_subject_key)
        if row is None:
            return

        if row.profile_id == profile_id:
            return

        row.profile_id = profile_id
        card = self.subject_cards.get(self.current_subject_key)
        if card:
            card.set_content(row.subject.name, self._subject_status_text(row))

        self._set_card_selection(profile_id)
        self._persist_and_sync()

    def reload(self, force_ci_reload: bool = False):
        previous_subject_key = self.current_subject_key

        if force_ci_reload and ci_manager:
            try:
                ci_manager.reload_config()
            except Exception as e:
                logger.warning(f"刷新 ClassIsland 配置失败: {e}")

        logger.debug("刷新关联页数据")
        self.subject_rows.clear()
        self.current_subject_key = None

        subjects = self.backend.list_subjects()
        for subject in subjects:
            key = self._subject_key(subject)
            profile_id = profile.get_profile_id_by_subject(
                provider=subject.provider,
                external_id=subject.external_id,
                name=subject.name,
            )
            self.subject_rows[key] = _SubjectRow(subject=subject, profile_id=profile_id)

        self._build_subject_cards()
        self._build_profile_cards()

        if self.subject_rows:
            target_key = (
                previous_subject_key if previous_subject_key in self.subject_rows else next(iter(self.subject_rows))
            )
            self._on_subject_selected(target_key)

    def open_with_profile(self, profile_id: str):
        self.preferred_profile_id = profile_id
        self.reload(force_ci_reload=True)

    def _persist_and_sync(self):
        old_guid_lookup: dict[str, str | None] = {}
        for binding in profile.list_bindings(provider=self.provider):
            for key in self._binding_keys(binding.subject):
                old_guid_lookup[key] = binding.managed_guid

        profile.clear_bindings(provider=self.provider)
        for key, row in self.subject_rows.items():
            if not row.profile_id:
                continue
            profile.set_binding(
                subject=SubjectRef(
                    provider=row.subject.provider,
                    external_id=row.subject.external_id,
                    name=row.subject.name,
                ),
                profile_id=row.profile_id,
                managed_guid=old_guid_lookup.get(key),
            )

        profile.save(PROFILE_PATH)

        result = self.backend.sync(profile)
        profile.save(PROFILE_PATH)

        if result.errors:
            content = "；".join(result.errors[:3])
            if len(result.errors) > 3:
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
