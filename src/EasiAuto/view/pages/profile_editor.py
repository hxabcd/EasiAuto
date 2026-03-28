from __future__ import annotations

from loguru import logger

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QListWidgetItem, QScroller, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    AvatarWidget,
    BodyLabel,
    CardWidget,
    CommandBar,
    FluentIcon,
    HorizontalSeparator,
    IconInfoBadge,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBoxBase,
    PasswordLineEdit,
    PrimaryPushButton,
    SubtitleLabel,
    SwitchButton,
    TransparentPushButton,
    VerticalSeparator,
)

from EasiAuto.common.consts import PROFILE_PATH
from EasiAuto.common.profile import EasiAutomation, profile
from EasiAuto.common.utils import create_shortcut
from EasiAuto.core.binding_sync import ClassIslandBindingBackend
from EasiAuto.integrations.classisland_manager import classisland_manager as ci_manager
from EasiAuto.view.components import SettingCard
from EasiAuto.view.components.qfw_widgets import ListWidget, PillOverflowBar, PillPushButton
from EasiAuto.view.components.setting_card import CardType
from EasiAuto.view.utils import get_main_container, get_main_window


class AdvancedOptionsDialog(MessageBoxBase):
    """高级选项"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("高级选项", self)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)

        # 初始化设置项
        self._init_settings()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.view)

        self.widget.setMinimumWidth(400)
        self.yesButton.setText("关闭")
        self.yesButton.clicked.connect(self.accept)
        self.cancelButton.hide()

    def _init_settings(self):
        """初始化设置项"""
        self.encrypt_card = SettingCard(
            card_type=CardType.SWITCH,
            icon=FluentIcon.VPN,
            title="启用档案密码加密",
            content="保存档案时对密码加密",
            is_item=True,
            item_margin=False,
        )
        self.encrypt_card.setChecked(profile.encryption_enabled)
        self.encrypt_card.valueChanged.connect(self._on_encryption_changed)
        self.vBoxLayout.addWidget(self.encrypt_card)

    def _on_encryption_changed(self, checked: bool):
        profile.encryption_enabled = checked
        profile.save(PROFILE_PATH)


class ProfileStatusBar(QWidget):
    """档案页状态栏"""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(54)

        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(16, 0, 16, 0)

        self.option_button = TransparentPushButton(icon=FluentIcon.DEVELOPER_TOOLS, text="高级选项")
        self.option_button.clicked.connect(self._show_advanced_options)

        layout.addWidget(SubtitleLabel("档案编辑"))
        layout.addStretch(1)
        layout.addWidget(self.option_button)

    def _show_advanced_options(self):
        dialog = AdvancedOptionsDialog(self.window())
        dialog.exec()


class ProfileCard(CardWidget):
    """档案卡片"""

    itemClicked = Signal(QListWidgetItem)
    actionRun = Signal(str)  # automation_id
    actionExport = Signal(str)  # automation_id
    actionRemove = Signal(QListWidgetItem)

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
        if self.automation and (img := self.automation.avatar):
            self.avatar_label.setImage(img)
        else:
            self.avatar_label.setText(self.automation.display_name or "?")

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
    def automation(self) -> EasiAutomation | None:
        if not self._automation_id:
            return None
        automation: EasiAutomation | None = self.list_item.data(Qt.ItemDataRole.UserRole)
        if automation and automation.id == self._automation_id:
            return automation
        return profile.get_automation(self._automation_id)

    def _update_subjects(self, tags: list[str]):
        self.subject_bar.setTags(tags)

    def _on_add_subject(self):
        # TODO: 跳转至对应科目
        window = get_main_window()
        window.switchTo(window.automation_page)

    @property
    def display_name(self) -> str:
        automation = self.automation
        if not automation:
            return "未命名自动化"
        return automation.name or automation.account_name or "未命名自动化"


    def _on_run(self):
        if self._automation_id:
            self.actionRun.emit(self._automation_id)

    def _on_export(self):
        if self._automation_id:
            self.actionExport.emit(self._automation_id)

    def update_display(self, automation: EasiAutomation):
        self._automation_id = automation.id
        self.name_label.setText(self.automation.display_name or "未命名自动化")
        self.detail_label.setText(self.automation.detail_name or "")
        subjects = profile.get_subjects_by_automation(automation.id)
        tags = [subject.name for subject in subjects]
        self._update_subjects(tags)
        self.enabled_switch.setChecked(automation.enabled)

    def _on_enabled_changed(self, enabled: bool):
        if self.automation:
            self.automation.enabled = enabled
            profile.save(PROFILE_PATH)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.itemClicked.emit(self.list_item)
        super().mousePressEvent(e)


class ProfileManagePage(QWidget):
    """档案编辑页"""

    profileChanged = Signal()
    runAutomation = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.current_automation: EasiAutomation | None = None
        self.current_list_item: QListWidgetItem | None = None
        self.is_new_automation = False
        self.binding_backend = ClassIslandBindingBackend()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

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

        self.editor_widget = QWidget()
        self.editor_layout = QVBoxLayout(self.editor_widget)

        self.new_auto_hint = CardWidget()
        self.new_auto_hint.setFixedHeight(44)
        hint_layout = QHBoxLayout(self.new_auto_hint)
        hint_layout.setContentsMargins(12, 2, 12, 2)
        hint_icon = IconInfoBadge.attension(FluentIcon.RINGER)
        hint_icon.setFixedSize(24, 24)
        hint_icon.setIconSize(QSize(12, 12))
        hint_text = BodyLabel("正在编辑新档案")
        hint_layout.addWidget(hint_icon)
        hint_layout.addWidget(hint_text)
        self.new_auto_hint.hide()

        self.automation_name_label = SubtitleLabel()

        self.form = QWidget()
        self.form.setStyleSheet("QLabel { font-size: 14px; margin-right: 4px; }")
        form_layout = QFormLayout(self.form)

        self.name_edit = LineEdit()
        self.account_edit = LineEdit()
        self.password_edit = PasswordLineEdit()
        self.account_name_edit = LineEdit()

        form_layout.addRow(BodyLabel("名称 (可选)"), self.name_edit)
        form_layout.addRow(BodyLabel("账号"), self.account_edit)
        form_layout.addRow(BodyLabel("密码"), self.password_edit)
        form_layout.addRow(BodyLabel("希沃用户名 (可选)"), self.account_name_edit)

        self.save_button = PrimaryPushButton("保存")
        self.save_button.clicked.connect(self._handle_save_automation)

        self.editor_layout.addWidget(self.new_auto_hint)
        self.editor_layout.addWidget(self.automation_name_label)
        self.editor_layout.addWidget(self.form)
        self.editor_layout.addStretch(1)
        self.editor_layout.addWidget(self.save_button)

        self.editor_widget.setDisabled(True)

        main_layout.addWidget(self.selector_widget, 1)
        main_layout.addWidget(VerticalSeparator())
        main_layout.addWidget(self.editor_widget, 1)

        layout.addLayout(main_layout, 1)

        self._init_selector()

    def _persist_profile(self):
        profile.save(PROFILE_PATH)

    def _sync_bindings(self):
        if not ci_manager:
            return

        result = self.binding_backend.sync(profile)
        profile.save(PROFILE_PATH)

        if result.errors:
            content = "；".join(result.errors[:3])
            if len(result.errors) > 3:
                content += "；..."
            InfoBar.error(
                title="关联同步存在失败项",
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
        self._clear_editor()

        for automation in profile.list_automations():
            self._add_automation_item(automation)

    def _add_automation_item(self, automation: EasiAutomation):
        item = QListWidgetItem(self.auto_list)

        item_widget = ProfileCard(item, automation.id)
        item_widget.itemClicked.connect(self._on_item_clicked)
        item_widget.actionRun.connect(self._handle_action_run)
        item_widget.actionExport.connect(self._handle_action_export)
        item_widget.actionRemove.connect(self._handle_action_remove)

        self.auto_list.setItemWidget(item, item_widget)
        item.setSizeHint(item_widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, automation)
        return item

    def _add_automation(self):
        self.is_new_automation = True
        self.current_automation = EasiAutomation(account="", password="")
        self.current_list_item = None
        self.auto_list.clearSelection()
        self._update_editor(self.current_automation)
        self.editor_widget.setEnabled(True)

    def _display_name(self, automation: EasiAutomation) -> str:
        return automation.name or automation.account_name or automation.account or "未命名档案"

    def _update_editor(self, automation: EasiAutomation):
        self.current_automation = automation
        self.new_auto_hint.setVisible(self.is_new_automation)
        self.automation_name_label.setText(self._display_name(automation))

        self.name_edit.setText(automation.name or "")
        self.account_edit.setText(automation.account)
        self.password_edit.setText(automation.password)
        self.account_name_edit.setText(automation.account_name or "")

        self.editor_widget.setEnabled(True)

    def _clear_editor(self):
        self.new_auto_hint.hide()
        self.automation_name_label.setText("")
        self.name_edit.clear()
        self.account_edit.clear()
        self.password_edit.clear()
        self.account_name_edit.clear()
        self.editor_widget.setDisabled(True)

    def _save_form(self):
        if not self.current_automation:
            raise ValueError("未选择档案")

        account = self.account_edit.text().strip()
        password = self.password_edit.text()

        if account == "":
            raise ValueError("账号不能为空")
        if password == "":
            raise ValueError("密码不能为空")

        existing = next((item for item in profile.list_automations() if item.account == account), None)
        if existing and existing.id != self.current_automation.id:
            raise ValueError("账号已存在")

        self.current_automation.name = self.name_edit.text().strip() or None
        self.current_automation.account = account
        self.current_automation.password = password
        self.current_automation.account_name = self.account_name_edit.text().strip() or None

        profile.upsert_automation(self.current_automation)
        self._persist_profile()

    def _handle_save_automation(self):
        try:
            self._save_form()
            self._sync_bindings()
        except ValueError as e:
            InfoBar.error(
                title="保存失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=get_main_container(),
            )
            return
        except Exception as e:
            logger.exception("保存档案时发生异常")
            InfoBar.error(
                title="保存失败",
                content=f"发生未知错误: {e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=get_main_container(),
            )
            return

        self.is_new_automation = False
        self._init_selector()

        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            automation = item.data(Qt.ItemDataRole.UserRole)
            if automation.id == self.current_automation.id:
                self.auto_list.setCurrentItem(item)
                self.current_list_item = item
                self._update_editor(automation)
                break

        self.profileChanged.emit()

        InfoBar.success(
            title="成功",
            content="档案已保存",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=1500,
            parent=get_main_container(),
        )

    def _on_item_clicked(self, item: QListWidgetItem):
        automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
        self.current_list_item = item
        self.is_new_automation = False
        self._update_editor(automation.model_copy(deep=True))

    def _handle_action_run(self, automation_id: str) -> None:
        if not (automation := profile.get_automation(automation_id)):
            logger.error(f"无法找到自动化: {automation_id}")

        self.runAutomation.emit(automation.account, automation.password)
        logger.info(f"信号已发送: 运行自动化 {automation.id}")

    def _handle_action_export(self, automation_id: str) -> None:
        if not (automation := profile.get_automation(automation_id)):
            logger.error(f"无法找到自动化: {automation_id}")

        create_shortcut(
            args=f'login --id "{automation.id}" --manual',
            name=automation.export_name,
            show_result_to=get_main_container(),
        )

    def _handle_action_remove(self, item: QListWidgetItem):
        automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
        if profile.delete_automation(automation.id):
            self._persist_profile()
            self._sync_bindings()
            if self.current_list_item == item:
                self.current_list_item = None
                self.current_automation = None
                self._clear_editor()
            self.auto_list.takeItem(self.auto_list.row(item))
            self.profileChanged.emit()
            InfoBar.success(
                title="成功",
                content="档案已删除",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1500,
                parent=get_main_container(),
            )

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
        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            automation: EasiAutomation | None = item.data(Qt.ItemDataRole.UserRole)
            item_widget = self.auto_list.itemWidget(item)
            if not isinstance(item_widget, ProfileCard) or automation is None:
                continue
            item_widget.update_display(automation)


class ProfilePage(QWidget):
    """设置 - 档案页"""

    profileChanged = Signal()
    runAutomation = Signal(str, str)

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
