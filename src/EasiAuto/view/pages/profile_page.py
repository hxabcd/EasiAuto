"""设置 - 档案页：列表选择器与档案编辑器的组装"""

from __future__ import annotations

from loguru import logger

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidgetItem,
    QScroller,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    CommandBar,
    FluentIcon,
    HorizontalSeparator,
    InfoBar,
    InfoBarPosition,
    VerticalSeparator,
)

from EasiAuto.core.utils import create_shortcut
from EasiAuto.integrations.classisland_manager import classisland_manager as ci_manager
from EasiAuto.models.profile import BaseAutomation, EasiAutomation, ProfileChangeReason, profile
from EasiAuto.services.binding_service import ClassIslandBindingBackend
from EasiAuto.view.components import ProfileCard, ProfileEditor, ProfileStatusBar
from EasiAuto.view.components.qfw_widgets import ListWidget
from EasiAuto.view.helpers import get_main_container


class ProfileManagePage(QWidget):
    """档案编辑页"""

    profileChanged = Signal()
    runAutomation = Signal(BaseAutomation)

    def __init__(self):
        super().__init__()
        self.current_list_item: QListWidgetItem | None = None
        self.binding_backend = ClassIslandBindingBackend()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # 左侧：档案列表选择器
        self.selector_widget = QWidget()
        self.selector_layout = QVBoxLayout(self.selector_widget)
        self.selector_layout.setContentsMargins(4, 0, 0, 8)

        self.action_bar = CommandBar()
        self.action_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.action_bar.addAction(Action(FluentIcon.ADD, "添加", triggered=self._add_automation))
        self.action_bar.addAction(Action(FluentIcon.SYNC, "刷新", triggered=self._init_selector))

        self.auto_list = ListWidget()
        self.auto_list.setSpacing(3)
        QScroller.grabGesture(self.auto_list.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.selector_layout.addWidget(self.action_bar)
        self.selector_layout.addWidget(self.auto_list)

        # 右侧：档案编辑器
        self.editor = ProfileEditor()

        main_layout.addWidget(self.selector_widget, 1)
        main_layout.addWidget(VerticalSeparator())
        main_layout.addWidget(self.editor, 1)

        layout.addLayout(main_layout, 1)

        self.editor.saveRequested.connect(self._on_editor_save_requested)
        self._init_selector()
        profile.notifier.changed.connect(self._on_profile_model_changed)

    def _sync_bindings(self):
        if not ci_manager:
            return

        # 读取当前 CI 绑定关系并提交，确保档案信息变更后自动化配置同步刷新
        desired_binding_map = self.binding_backend.get_binding_map()
        ok = self.binding_backend.sync(desired_binding_map)

        if not ok:
            errors = self.binding_backend.last_errors
            content = "；".join(errors[:3]) if errors else "请检查 ClassIsland 状态与配置"
            if len(errors) > 3:
                content += "；..."
            InfoBar.error(
                title="同步自动化失败",
                content=content,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=get_main_container(),
            )

    def _init_selector(self):
        self.current_list_item = None
        self.auto_list.clear()
        self.editor.clear()

        for automation in profile.list_automation():
            self._add_automation_item(automation)
        self.refresh_binding_display()

    def _add_automation_item(self, automation: BaseAutomation):
        item = QListWidgetItem(self.auto_list)

        item_widget = ProfileCard(item, automation.id)
        item_widget.itemClicked.connect(self._on_item_clicked)
        item_widget.actionRun.connect(self._handle_action_run)
        item_widget.actionExport.connect(self._handle_action_export)
        item_widget.actionRemove.connect(self._handle_action_remove)
        item_widget.enabledChanged.connect(self._handle_action_enabled_changed)

        self.auto_list.setItemWidget(item, item_widget)
        item.setSizeHint(item_widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, automation)
        return item

    def _add_automation(self):
        self.current_list_item = None
        self.auto_list.clearSelection()
        self.editor.start_new()

    def _on_item_clicked(self, item: QListWidgetItem):
        automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
        self.current_list_item = item
        self.editor.load(automation.model_copy(deep=True))

    def _on_editor_save_requested(self, automation: BaseAutomation):
        """持久化编辑器提交的档案并刷新界面"""
        profile.upsert_automation(automation)
        profile.save(reason="automation_saved")

        self._init_selector()

        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            current = item.data(Qt.ItemDataRole.UserRole)
            if current.id == automation.id:
                self.auto_list.setCurrentItem(item)
                self.current_list_item = item
                self.editor.load(current)
                break

        self.profileChanged.emit()

    def _handle_action_run(self, automation_id: str) -> None:
        if not (automation := profile.get_automation(automation_id)):
            logger.error(f"无法找到自动化: {automation_id}")
            return

        self.runAutomation.emit(automation)
        logger.info(f"信号已发送: 运行自动化 {automation.id}")

    def _handle_action_export(self, automation_id: str) -> None:
        if not (automation := profile.get_automation(automation_id)):
            logger.error(f"无法找到自动化: {automation_id}")
            return

        create_shortcut(
            args=f'login --id "{automation.id}" --manual',
            name=automation.export_name,
            icon_name="EasiAutoShortcut",
            show_result_to=get_main_container(),
        )

    def _handle_action_enabled_changed(self, automation_id: str, enabled: bool) -> None:
        if not (automation := profile.get_automation(automation_id)):
            logger.error(f"无法找到自动化: {automation_id}")
            return

        if automation.enabled == enabled:
            return

        automation.enabled = enabled
        profile.save(reason="automation_saved")

    def _handle_action_remove(self, item: QListWidgetItem):
        automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
        if profile.delete_automation(automation.id):
            profile.save(reason="automation_deleted")
            if self.current_list_item == item:
                self.current_list_item = None
                self.editor.clear()
            self.auto_list.takeItem(self.auto_list.row(item))
            self.profileChanged.emit()

    def scroll_to_automation(self, automation_id: str):
        """跳转并选中指定的自动化档案"""
        target_item = None

        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
            if automation and automation.id == automation_id:
                target_item = item
                break

        if target_item:
            self.auto_list.setCurrentItem(target_item)
            self.auto_list.scrollToItem(target_item)

            self._on_item_clicked(target_item)

            logger.info(f"已跳转到档案编辑: {automation_id}")
            return True
        logger.warning(f"跳转失败: 找不到 ID 为 {automation_id} 的档案")
        return False

    def refresh_binding_display(self):
        subject_tags_map = self._build_subject_tags_map()
        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            automation: EasiAutomation | None = item.data(Qt.ItemDataRole.UserRole)
            item_widget = self.auto_list.itemWidget(item)
            if not isinstance(item_widget, ProfileCard) or automation is None:
                continue
            item_widget.update_display(automation)
            item_widget.set_subject_tags(subject_tags_map.get(automation.id, []))

    def _build_subject_tags_map(self) -> dict[str, list[str]]:
        if not ci_manager:
            return {}

        subjects = self.binding_backend.list_subjects()
        subject_name_map = {item.id: item.name for item in subjects if item.id}
        binding_map = self.binding_backend.get_binding_map()

        subject_tags_map: dict[str, list[str]] = {}
        for subject_id, automation_id in binding_map.items():
            if subject_name := subject_name_map.get(subject_id):
                subject_tags_map.setdefault(automation_id, []).append(subject_name)
        return subject_tags_map

    def _on_profile_model_changed(self, reason: ProfileChangeReason):
        if reason in {"automation_saved", "automation_deleted"}:
            self._sync_bindings()
            self.refresh_binding_display()


class ProfilePage(QWidget):
    """设置 - 档案页"""

    profileChanged = Signal()
    runAutomation = Signal(BaseAutomation)

    def __init__(self):
        super().__init__()
        logger.debug("初始化档案页")
        self.setObjectName("ProfilePage")
        self.setStyleSheet("border: none; background-color: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.status_bar = ProfileStatusBar()
        self.manager_page = ProfileManagePage()
        self.manager_page.profileChanged.connect(self.profileChanged.emit)
        self.manager_page.runAutomation.connect(self.runAutomation.emit)

        layout.addWidget(self.status_bar)
        layout.addWidget(HorizontalSeparator())
        layout.addWidget(self.manager_page)