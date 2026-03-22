from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QScroller, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    BodyLabel,
    CardWidget,
    CommandBar,
    FluentIcon,
    HorizontalSeparator,
    InfoBar,
    InfoBarPosition,
    RadioButton,
    SmoothScrollArea,
    SubtitleLabel,
    VerticalSeparator,
)

from EasiAuto.common.consts import PROFILE_PATH
from EasiAuto.common.profile import SubjectRef, profile
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
            self.setStyleSheet("CardWidget { border: 1px solid rgba(120, 120, 120, 0.35); border-radius: 8px; }")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.subjectClicked.emit(self.key)
        super().mousePressEvent(event)

    # def resizeEvent(self, event):
    #     target = max(100, int(self.width() * 2 / 3))
    #     if abs(self.height() - target) > 1:
    #         self.setFixedHeight(target)
    #     super().resizeEvent(event)


class BindingStatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)

        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(16, 0, 16, 0)

        self.action_bar = CommandBar()
        self.action_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.action_refresh = Action(FluentIcon.SYNC, "刷新")
        self.action_bar.addAction(self.action_refresh)

        layout.addWidget(SubtitleLabel("科目关联"))
        layout.addStretch(1)
        layout.addWidget(self.action_bar)


class SubjectBindingPage(QWidget):
    bindingsChanged = Signal()
    provider = "classisland"

    def __init__(self):
        super().__init__()
        self.setObjectName("BindingPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        self.backend = ClassIslandBindingBackend()
        self.subject_rows: dict[str, _SubjectRow] = {}
        self.subject_cards: dict[str, SubjectCard] = {}
        self.current_subject_key: str | None = None
        self.preferred_profile_id: str | None = None
        self._updating_radios = False

        self.profile_button_group = QButtonGroup(self)
        self.profile_button_group.setExclusive(True)
        self.profile_button_group.buttonClicked.connect(self._on_profile_radio_clicked)

        self._setup_ui()
        self.reload()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.status_bar = BindingStatusBar()
        self.status_bar.action_refresh.triggered.connect(lambda: self.reload(force_ci_reload=True))

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

        layout.addWidget(self.status_bar)
        layout.addWidget(HorizontalSeparator())
        layout.addWidget(main, 1)

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
    def _profile_display_name(automation) -> str:
        label = automation.name or automation.account_name or automation.account or "未命名档案"
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

    def _clear_profile_radios(self):
        while self.profile_layout.count():
            item = self.profile_layout.takeAt(0)
            widget = item.widget()
            if widget:
                self.profile_button_group.removeButton(widget)
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

    def _build_profile_radios(self):
        self._clear_profile_radios()

        radio_unbound = RadioButton("未绑定")
        radio_unbound.setProperty("profile_id", None)
        self.profile_button_group.addButton(radio_unbound)
        self.profile_layout.addWidget(radio_unbound)

        for automation in profile.list_automations():
            radio = RadioButton(self._profile_display_name(automation))
            radio.setProperty("profile_id", automation.id)
            self.profile_button_group.addButton(radio)
            self.profile_layout.addWidget(radio)

        self.profile_layout.addStretch(1)

    def _set_radio_selection(self, profile_id: str | None):
        self._updating_radios = True
        target_found = False
        for button in self.profile_button_group.buttons():
            pid = button.property("profile_id")
            matched = pid == profile_id
            button.setChecked(matched)
            if matched:
                target_found = True
        if not target_found:
            for button in self.profile_button_group.buttons():
                if button.property("profile_id") is None:
                    button.setChecked(True)
                    break
        self._updating_radios = False

    def _on_subject_selected(self, subject_key: str):
        self.current_subject_key = subject_key
        for key, card in self.subject_cards.items():
            card.set_selected(key == subject_key)

        row = self.subject_rows.get(subject_key)
        if row is None:
            self._set_radio_selection(None)
            return

        current_profile_id = row.profile_id
        if current_profile_id is None and self.preferred_profile_id is not None:
            current_profile_id = self.preferred_profile_id
        self._set_radio_selection(current_profile_id)

    def _on_profile_radio_clicked(self, _button=None):
        if self._updating_radios or not self.current_subject_key:
            return

        row = self.subject_rows.get(self.current_subject_key)
        if row is None:
            return

        checked = self.profile_button_group.checkedButton()
        if checked is None:
            return

        profile_id = checked.property("profile_id")
        profile_id = profile_id if isinstance(profile_id, str) else None
        if row.profile_id == profile_id:
            return

        row.profile_id = profile_id
        card = self.subject_cards.get(self.current_subject_key)
        if card:
            card.set_content(row.subject.name, self._subject_status_text(row))

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
        self._build_profile_radios()

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
