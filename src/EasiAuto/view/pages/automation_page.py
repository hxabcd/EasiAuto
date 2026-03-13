import contextlib
from enum import Enum
from pathlib import Path
from typing import assert_never

from loguru import logger

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QListWidgetItem,
    QScroller,
    QStackedLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CardWidget,
    ComboBox,
    CommandBar,
    DotInfoBadge,
    FluentIcon,
    HorizontalSeparator,
    IconInfoBadge,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    InfoLevel,
    LineEdit,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    SubtitleLabel,
    SwitchButton,
    TitleLabel,
    TransparentPushButton,
    VerticalSeparator,
)

from EasiAuto.common import utils
from EasiAuto.common.config import config
from EasiAuto.core.manager import automation_manager
from EasiAuto.integrations.classisland_manager import EasiAutomation, manager
from EasiAuto.view.components import SettingCard, SmallStatusOverlay, StatusOverlay, WarningBanner
from EasiAuto.view.components.qfw_widgets import ListWidget
from EasiAuto.view.utils import get_main_container, get_main_window, set_enable_by


class AdvancedOptionsDialog(MessageBoxBase):
    """高级选项对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("高级选项", self)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)

        # 初始化设置项
        self._init_settings()

        # 添加到内容布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.view)

        # 设置对话框属性
        self.widget.setMinimumWidth(400)
        self.yesButton.setText("关闭")
        self.yesButton.clicked.connect(self.accept)
        self.cancelButton.hide()

    def _init_settings(self):
        """初始化设置项"""
        config_group = config.iter_items(only=["ClassIsland"])[0]

        for item in config_group.children:
            card = SettingCard.from_config(item, is_item=True, item_margin=False)
            self.vBoxLayout.addWidget(card)
            if isinstance(card.widget, LineEdit):
                card.widget.setMinimumWidth(200)

        set_enable_by(
            SettingCard.index["ClassIsland.Path"],
            SettingCard.index["ClassIsland.AutoPath"].widget,  # type: ignore
            reverse=True,
        )


class CIStatus(Enum):
    UNINITIALIZED = -1
    DIED = 0
    RUNNING = 1


class AutomationStatusBar(QWidget):
    """自动化页 - 状态栏"""

    def __init__(self):
        super().__init__()

        self.setFixedHeight(54)
        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(16, 0, 16, 0)

        self.status_badge = DotInfoBadge.error()
        self.status_label = BodyLabel("未初始化")

        self.action_button = PushButton(icon=FluentIcon.POWER_BUTTON, text="终止")
        self.action_button.clicked.connect(self.handle_action_button_clicked)
        self.action_button.setEnabled(False)

        self.option_button = TransparentPushButton(icon=FluentIcon.DEVELOPER_TOOLS, text="高级选项")
        self.option_button.clicked.connect(self._show_advanced_settings)

        layout.addWidget(SubtitleLabel("ClassIsland 自动化编辑"))
        layout.addSpacing(12)
        layout.addWidget(self.status_badge)
        layout.addWidget(self.status_label)
        layout.addSpacing(6)
        layout.addWidget(self.action_button)
        layout.addStretch(1)
        layout.addWidget(self.option_button)

        self.update_status()

    def _show_advanced_settings(self):
        """显示高级设置对话框"""
        w = AdvancedOptionsDialog(self.window())
        w.exec()

    def update_status(self, status: CIStatus | None = None):
        if status is None:
            if manager:
                status = CIStatus.RUNNING if manager.is_ci_running else CIStatus.DIED
            else:
                status = CIStatus.UNINITIALIZED

        match status:
            case CIStatus.UNINITIALIZED:
                self.status_badge.level = InfoLevel.ERROR
                self.status_badge.update()
                self.status_label.setText("未初始化")
                self.action_button.setEnabled(False)
            case CIStatus.RUNNING:
                self.status_badge.level = InfoLevel.SUCCESS
                self.status_badge.update()
                self.status_label.setText("运行中")
                self.action_button.setText("终止")
                self.action_button.setEnabled(True)
            case CIStatus.DIED:
                self.status_badge.level = InfoLevel.INFOAMTION
                self.status_badge.update()
                self.status_label.setText("未运行")
                self.action_button.setText("启动")
                self.action_button.setEnabled(True)
            case unreachable:
                assert_never(unreachable)

    def handle_action_button_clicked(self):
        if not manager:
            return
        if manager.is_ci_running:
            logger.info("终止 ClassIsland")
            manager.close_ci()
        else:
            logger.info("启动 ClassIsland")
            manager.open_ci()


class AutomationCard(CardWidget):
    """自动化项目的卡片组件"""

    itemClicked = Signal(QListWidgetItem)
    switchEnabledChanged = Signal(str, bool)  # 参数：automation_guid, is_enabled
    actionRun = Signal(str)  # 参数：automation_guid
    actionExport = Signal(str)  # 参数：automation_guid
    actionRemove = Signal(QListWidgetItem)

    def __init__(self, item: QListWidgetItem, automation: EasiAutomation | None = None):
        super().__init__()
        self.title = "自动化"
        self.list_item = item
        self.automation = automation  # 保留引用用于初始化

        self.init_ui()

        if automation:
            self.update_display(automation)

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 信息栏
        self.info_bar = QWidget()
        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.name_label = BodyLabel(self.title)
        self.switch = SwitchButton()
        self.switch.setOnText("启用")
        self.switch.setOffText("禁用")
        self.switch.checkedChanged.connect(self.on_switch_toggled)

        info_layout.addWidget(self.name_label)
        info_layout.addStretch(1)
        info_layout.addWidget(self.switch)

        # 操作栏
        self.command_bar = CommandBar()
        self.command_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.action_run = Action(FluentIcon.PLAY, "运行", triggered=self._on_run)
        self.action_export = Action(FluentIcon.SHARE, "导出", triggered=self._on_export)
        self.action_remove = Action(
            FluentIcon.CANCEL_MEDIUM,
            "删除",
            triggered=lambda: self.actionRemove.emit(self.list_item),
        )

        self.command_bar.addAction(self.action_run)
        self.command_bar.addAction(self.action_export)
        self.command_bar.addAction(self.action_remove)

        layout.addWidget(self.info_bar)
        layout.addWidget(self.command_bar)

        # 设置鼠标事件
        self.setMouseTracking(True)

    def on_switch_toggled(self, checked: bool):
        """开关状态改变时，发出信号通知父级处理"""
        if self.automation:
            logger.debug(f"自动化 {self.automation.guid} 启用状态改变: {checked}")
            self.switchEnabledChanged.emit(self.automation.guid, checked)

    def _on_run(self):
        """运行按钮点击"""
        if self.automation:
            self.actionRun.emit(self.automation.guid)

    def _on_export(self):
        """导出按钮点击"""
        if self.automation:
            self.actionExport.emit(self.automation.guid)

    def update_display(self, automation: EasiAutomation):
        """更新卡片显示（不修改数据）"""
        logger.debug(f"更新自动化卡片显示: {automation.item_display_name}")
        self.automation = automation
        self.name_label.setText(automation.item_display_name)
        # 断开连接以避免触发信号
        self.switch.checkedChanged.disconnect()
        self.switch.setChecked(automation.enabled)
        self.switch.checkedChanged.connect(self.on_switch_toggled)

    def mousePressEvent(self, e):
        """鼠标点击事件"""
        if e.button() == Qt.MouseButton.LeftButton:
            self.itemClicked.emit(self.list_item)
        super().mousePressEvent(e)


class AutomationManageSubpage(QWidget):
    """自动化页 - 自动化管理 子页面"""

    def __init__(self):
        super().__init__()
        self.current_automation: EasiAutomation | None = None
        self.current_list_item = None
        self.is_new_automation = False  # 标记是否在编辑新自动化

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 左侧：选择器
        self.selector_widget = QWidget()
        self.selector_layout = QVBoxLayout(self.selector_widget)
        self.selector_layout.setContentsMargins(8, 0, 8, 12)

        self.action_bar = CommandBar()
        self.action_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.action_bar.addAction(Action(FluentIcon.ADD, "添加", triggered=self._add_automation))
        self.action_bar.addAction(
            Action(
                FluentIcon.SYNC,
                "刷新",
                triggered=lambda: self._init_selector(reload=True),
            )
        )

        self.auto_list = ListWidget()
        self.auto_list.setSpacing(3)
        QScroller.grabGesture(self.auto_list.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.selector_layout.addWidget(self.action_bar)
        self.selector_layout.addWidget(self.auto_list)

        # 右侧：容器 (包含编辑器和浮层)
        self.right_container = QWidget()
        self.right_layout = QStackedLayout(self.right_container)
        self.right_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)

        # 编辑器
        self.editor_widget = QWidget()
        self.editor_layout = QVBoxLayout(self.editor_widget)

        # 新自动化提示
        self.new_auto_hint = CardWidget()

        self.new_auto_hint.setFixedHeight(48)
        self.new_auto_hint.setContentsMargins(12, 2, 12, 2)
        hint_layout = QHBoxLayout(self.new_auto_hint)
        hint_icon = IconInfoBadge.attension(FluentIcon.RINGER)
        hint_icon.setFixedSize(24, 24)
        hint_icon.setIconSize(QSize(12, 12))
        hint_text = BodyLabel("正在编辑新自动化")
        hint_text.setStyleSheet("font-size: 14px;")
        hint_layout.addWidget(hint_icon)
        hint_layout.addWidget(hint_text)
        self.new_auto_hint.setVisible(False)
        self.editor_layout.addWidget(self.new_auto_hint)

        # 自动化名称标签
        self.automation_name_label = SubtitleLabel()
        self.editor_layout.addWidget(self.automation_name_label)

        # 编辑表单
        self.form = QWidget()
        self.form.setStyleSheet("QLabel { font-size: 14px; margin-right: 4px; }")
        form_layout = QFormLayout(self.form)

        self.account_edit = LineEdit()
        self.password_edit = LineEdit()
        self.subject_edit = ComboBox()
        self.teacher_edit = LineEdit()
        self.pretime_edit = SpinBox()

        form_layout.addRow(BodyLabel("账号"), self.account_edit)
        form_layout.addRow(BodyLabel("密码"), self.password_edit)
        form_layout.addRow(BodyLabel("科目"), self.subject_edit)
        form_layout.addRow(BodyLabel("教师 (可选)"), self.teacher_edit)
        form_layout.addRow(BodyLabel("提前时间 (秒)"), self.pretime_edit)

        self.subject_edit.setCurrentIndex(-1)
        self.pretime_edit.setRange(0, 900)

        self.save_button = PrimaryPushButton("保存")
        self.save_button.clicked.connect(self._handle_save_automation)

        self.editor_layout.addWidget(self.form)
        self.editor_layout.addStretch(1)
        self.editor_layout.addWidget(self.save_button)
        self.editor_widget.setDisabled(True)

        # 浮层
        self.overlay = CiRunningWarnOverlay(self.right_container)
        self.overlay.hide()

        self.right_layout.addWidget(self.editor_widget)
        self.right_layout.addWidget(self.overlay)

        layout.addWidget(self.selector_widget, 1)
        layout.addWidget(VerticalSeparator())
        layout.addWidget(self.right_container, 1)

        if manager:
            # 订阅 Manager 的数据变更信号
            manager.automationCreated.connect(self._on_automation_created)
            manager.automationUpdated.connect(self._on_automation_updated)
            manager.automationDeleted.connect(self._on_automation_deleted)
            self._init_selector()
            self._init_editor()
            self.set_ci_running_state(manager.is_ci_running)

    def set_ci_running_state(self, running: bool):
        """设置 CI 运行状态，控制浮层和按钮"""
        self.overlay.setVisible(running)
        if running:
            self.overlay.raise_()

        # 禁用/启用编辑
        self.new_auto_hint.setDisabled(running)
        if running:
            self.automation_name_label.setTextColor(light=QColor(150, 150, 150), dark=QColor(200, 200, 200))
        else:
            self.automation_name_label.setTextColor()
        self.form.setDisabled(running)
        self.save_button.setDisabled(running)
        if self.action_bar.actions():
            self.action_bar.actions()[0].setDisabled(running)
        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            widget = self.auto_list.itemWidget(item)
            if isinstance(widget, AutomationCard):
                widget.action_remove.setDisabled(running)
                widget.switch.setDisabled(running)

    def _init_selector(self, reload: bool = False):
        """初始化自动化列表"""
        if not manager:
            return

        if reload:
            manager.reload_config()

        self.current_list_item = None
        self._clear_editor()

        self.auto_list.clear()

        for _, automation in manager.automations.items():
            self._add_automation_item(automation)

        self.set_ci_running_state(manager.is_ci_running)

    def _add_automation_item(self, automation: EasiAutomation):
        """添加自动化项目到列表"""
        item = QListWidgetItem(self.auto_list)
        item.setSizeHint(QSize(270, 96))

        item_widget = AutomationCard(item, automation)
        item_widget.itemClicked.connect(self._on_item_clicked)
        item_widget.switchEnabledChanged.connect(self._on_automation_enabled_changed)
        item_widget.actionRun.connect(self._handle_action_run)
        item_widget.actionExport.connect(self._handle_action_export)
        item_widget.actionRemove.connect(self._handle_action_remove)

        # 将组件设置到列表项
        self.auto_list.setItemWidget(item, item_widget)

        # 保存数据到 item
        item.setData(Qt.ItemDataRole.UserRole, automation)

        return item

    def _add_automation(self):
        """添加新的自动化"""
        if not manager:
            logger.warning("无法添加自动化: 管理器未初始化")
            return

        logger.info("添加新的自动化")
        # 创建临时对象用于编辑，但不添加到列表
        automation = EasiAutomation(account="", password="", subject_id="")
        self.is_new_automation = True
        self.current_automation = automation
        self.current_list_item = None
        self.auto_list.clearSelection()

        # 确保科目列表已初始化
        if self.subject_edit.count() == 0:
            self._init_editor()

        self._update_editor(automation)
        self.editor_widget.setEnabled(True)

    def _init_editor(self, reload: bool = False):
        """初始化编辑器与科目"""
        if not manager:
            return

        if reload:
            manager.reload_config()

        self.subject_edit.clear()

        for subject in manager.list_subjects():
            self.subject_edit.addItem(subject.name, userData=subject.id)

    def _update_editor(self, auto: EasiAutomation):
        """更新编辑器数据"""
        self.current_automation = auto

        self.new_auto_hint.setVisible(self.is_new_automation)
        self.automation_name_label.setText(auto.item_display_name)

        self.account_edit.setText(auto.account)
        self.password_edit.setText(auto.password)

        self.subject_edit.setCurrentIndex(-1)
        if manager:
            subject = manager.get_subject_by_id(auto.subject_id)
            if subject:
                subject_item = self.subject_edit.findData(subject.id)
                if subject_item != -1:
                    self.subject_edit.setCurrentIndex(subject_item)

        self.teacher_edit.setText(auto.teacher_name)
        self.pretime_edit.setValue(auto.pretime)

        self.editor_widget.setEnabled(auto.enabled)

    def _clear_editor(self):
        """清空编辑器数据"""
        self.automation_name_label.setText("")
        self.account_edit.clear()
        self.password_edit.clear()
        self.subject_edit.setCurrentIndex(-1)
        self.teacher_edit.clear()
        self.pretime_edit.setValue(0)

        self.editor_widget.setDisabled(True)

    def _save_form(self):
        """保存编辑器数据"""
        if not manager or not self.current_automation:
            return

        automation = self.current_automation

        # 验证并收集数据
        automation.account = self.account_edit.text()
        if automation.account == "":
            raise ValueError("账号不能为空")

        automation.password = self.password_edit.text()
        if automation.password == "":
            raise ValueError("密码不能为空")

        subject_id = self.subject_edit.currentData()
        if subject_id is None:
            raise ValueError("未选择科目")
        if manager.get_subject_by_id(subject_id) is None:
            raise ValueError("无效科目")
        automation.subject_id = subject_id

        automation.teacher_name = self.teacher_edit.text()
        automation.pretime = self.pretime_edit.value()

        # 通过 Manager 保存，不直接修改 item
        if manager.get_automation_by_guid(automation.guid) is None:
            # 新建
            manager.create_automation(automation)
        else:
            # 更新
            manager.update_automation(automation.guid, **automation.model_dump())

    def _handle_save_automation(self):
        """保存自动化数据"""
        if not manager or not self.current_automation:
            return
        try:
            logger.debug("保存自动化数据")
            self._save_form()
            logger.success("自动化数据保存成功")
            # 更新状态
            self.current_automation = manager.get_automation_by_guid(self.current_automation.guid)
            self.is_new_automation = False
            if self.current_automation:
                self._update_editor(self.current_automation)
        except ValueError as e:
            logger.warning(f"自动化数据保存失败: {e}")
            InfoBar.error(
                title="错误",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=get_main_container(),
            )

    def _on_item_clicked(self, item: QListWidgetItem):
        """列表项点击事件"""
        automation = item.data(Qt.ItemDataRole.UserRole)
        logger.debug(f"点击自动化项目: {automation.item_display_name}")
        self.current_list_item = item

        self.is_new_automation = False
        self._update_editor(automation)

    def _on_automation_enabled_changed(self, guid: str, enabled: bool):
        """处理 Card 中开关状态改变（通过 Manager 更新）"""
        logger.debug(f"自动化启用状态改变 - GUID: {guid}, 启用: {enabled}")
        if manager:
            manager.update_automation(guid, enabled=enabled)

    def _handle_action_run(self, guid: str):
        """操作 - 运行自动化"""
        if not manager:
            logger.warning("无法运行自动化: 管理器未初始化")
            return

        automation = manager.get_automation_by_guid(guid)
        if not automation:
            logger.error(f"无法找到自动化: {guid}")
            return

        logger.info(f"开始运行自动化: {automation.item_display_name}")

        # 最小化设置界面
        if instance := get_main_window():
            instance.showMinimized()

        # NOTE: 下方运行逻辑在 launcher.py _start_login() 中存在相同实现，如更改需同步替换

        if config.Banner.Enabled:
            try:
                width = utils.get_screen_size()[0]
                self.banner = WarningBanner(config.Banner.Style)
                self.banner.setGeometry(0, 80, width, 140)
                self.banner.show()
            except Exception as e:
                logger.error(f"显示横幅时出错，跳过横幅：{e}")

        logger.debug(f"当前设置的登录方案: {config.Login.Method}")
        automation_manager.finished.connect(self._handle_finish)
        automation_manager.failed.connect(self._handle_finish)

        if config.StatusOverlay.Enabled:
            screen_height = utils.get_screen_size()[1]
            login_window_buttom = utils.calc_relative_login_window_position(
                utils.Point(config.Login.Position.AgreementCheckbox),
                window_size=config.Login.Position.LoginWindowSize,
                base_size=config.Login.Position.BaseSize,
            ).y
            available_space = screen_height - (login_window_buttom + 8)
            try:
                self.status_overlay = StatusOverlay() if available_space > 300 else SmallStatusOverlay()
                self.status_overlay.stop_clicked.connect(automation_manager.stop)
                automation_manager.started.connect(self.status_overlay.show)
                automation_manager.finished.connect(self.status_overlay.on_finished)
                automation_manager.failed.connect(self.status_overlay.on_failed)
                automation_manager.task_update.connect(self.status_overlay.set_task_text)
                automation_manager.progress_update.connect(self.status_overlay.set_progress_text)
            except Exception as e:
                logger.error(f"设置状态浮窗时出错，跳过状态浮窗：{e}")

        automation_manager.run(automation.account, automation.password)

    def _handle_finish(self, error_message: str | None = None):
        if hasattr(self, "banner"):
            self.banner.close()
            self.banner.deleteLater()
            self.banner = None
        if hasattr(self, "status_overlay"):
            QTimer.singleShot(3000, self.status_overlay.close)
            QTimer.singleShot(3000, self.status_overlay.deleteLater)
            QTimer.singleShot(3000, lambda: setattr(self, "status_overlay", None))

        if error_message:
            InfoBar.error(
                title="自动登录失败",
                content=error_message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=get_main_container(),
            )
        else:
            InfoBar.success(
                title="成功",
                content="自动登录已完成",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=get_main_container(),
            )

        logger.success("自动化运行结束")

    def _handle_action_export(self, guid: str):
        """操作 - 导出自动化"""
        if not manager:
            logger.warning("无法导出自动化: 管理器未初始化")
            return

        automation = manager.get_automation_by_guid(guid)
        if not automation:
            logger.error(f"无法找到自动化: {guid}")
            return

        utils.create_shortcut(
            args=f'login --account "{automation.account}" --password "{automation.password}" --manual',
            name=automation.shortcut_name,
            show_result_to=get_main_container(),
        )

    def _handle_action_remove(self, item: QListWidgetItem):
        """操作 - 删除自动化"""
        if not manager:
            logger.warning("无法删除自动化: 管理器未初始化")
            return

        automation = item.data(Qt.ItemDataRole.UserRole)
        logger.info(f"删除自动化: {automation.item_display_name}")
        manager.delete_automation(automation.guid)

    def _on_automation_created(self, guid: str):
        """Manager 信号：自动化被创建"""
        logger.debug(f"收到自动化创建信号: {guid}")
        if not manager:
            logger.warning("无法创建自动化: 管理器未初始化")
            return

        automation = manager.get_automation_by_guid(guid)
        if not automation:
            logger.error(f"无法获取新创建的自动化: {guid}")
            return

        logger.success(f"自动化已创建: {automation.item_display_name}")
        # 添加到列表
        item = self._add_automation_item(automation)
        # 如果是新建的自动化，自动选中
        if self.is_new_automation:
            self.auto_list.setCurrentItem(item)
            self.current_list_item = item

    def _on_automation_updated(self, guid: str):
        """Manager 信号：自动化被更新"""
        logger.debug(f"收到自动化更新信号: {guid}")
        if not manager:
            logger.warning("管理器未初始化")
            return

        automation = manager.get_automation_by_guid(guid)
        if not automation:
            logger.error(f"无法获取已更新的自动化: {guid}")
            return

        logger.debug(f"自动化已更新: {automation.item_display_name}")
        # 找到对应的列表项并更新
        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            card_widget = self.auto_list.itemWidget(item)
            if item.data(Qt.ItemDataRole.UserRole).guid == guid:
                # 更新 item 数据
                item.setData(Qt.ItemDataRole.UserRole, automation)
                # 更新 Card 显示
                if card_widget:
                    card_widget.update_display(automation)
                # 如果是当前编辑的项，也更新编辑器
                if self.current_list_item == item:
                    self._update_editor(automation)
                break

    def _on_automation_deleted(self, guid: str):
        """Manager 信号：自动化被删除"""
        logger.debug(f"收到自动化删除信号: {guid}")
        # 从列表中移除
        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole).guid == guid:
                # 如果删除的是当前项，清空编辑器
                if self.current_list_item == item:
                    self.current_list_item = None
                    self._clear_editor()
                automation_name = item.data(Qt.ItemDataRole.UserRole).item_display_name
                self.auto_list.takeItem(i)
                logger.info(f"自动化已删除: {automation_name}")
                break

    def init_manager(self):
        """重设 ClassIsland 管理器"""
        if not manager:
            return
        manager.automationCreated.connect(self._on_automation_created)
        manager.automationUpdated.connect(self._on_automation_updated)
        manager.automationDeleted.connect(self._on_automation_deleted)
        self._init_selector()
        self._init_editor()


class PathSelectSubpage(QWidget):
    """自动化页 - 路径选择 子页面"""

    pathChanged = Signal(Path)

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_container = QHBoxLayout()
        icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_icon = IconWidget(FluentIcon.REMOVE_FROM)
        hint_icon.setFixedSize(96, 96)
        icon_container.addWidget(hint_icon)

        hint_label = TitleLabel("未能获取到 ClassIsland 路径")
        hint_desc = BodyLabel("<span style='font-size: 15px;'>EasiAuto 的「自动化」功能依赖于 ClassIsland</span>")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions = QWidget()

        actions_layout = QHBoxLayout(actions)
        actions_layout.setSpacing(10)

        get_ci_button = PrimaryPushButton(icon=FluentIcon.DOWNLOAD, text="获取 ClassIsland")
        get_ci_button.setFixedWidth(150)
        get_ci_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://classisland.tech")))

        browse_button = PushButton(icon=FluentIcon.FOLDER_ADD, text="选择已有路径")
        browse_button.setFixedWidth(150)
        browse_button.clicked.connect(self.browse_ci_path)

        actions_layout.addWidget(get_ci_button)
        actions_layout.addWidget(BodyLabel("或"))
        actions_layout.addWidget(browse_button)

        layout.addLayout(icon_container)
        layout.addSpacing(12)
        layout.addWidget(hint_label)
        layout.addWidget(hint_desc)
        layout.addSpacing(18)
        layout.addWidget(actions)

    def browse_ci_path(self):
        logger.debug("打开文件选择对话框")
        exe_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 ClassIsland 程序路径",
            "D:/" if Path("D:/").exists() else "C:/",
            "ClassIsland 可执行文件 (*.exe)",
        )

        if not exe_path:  # 取消选择
            logger.debug("取消文件选择")
            return

        logger.info(f"选择 ClassIsland 路径: {exe_path}")
        exe_path = Path(exe_path)
        if exe_path.exists():
            InfoBar.info(
                title="信息",
                content="已关闭自动路径获取",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=get_main_container(),
            )
            config.ClassIsland.AutoPath = False
            config.ClassIsland.Path = str(exe_path)
            self.pathChanged.emit(exe_path)
        else:
            logger.error("选择的路径不存在")
            InfoBar.error(
                title="错误",
                content="选择的路径不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=get_main_container(),
            )


class CiRunningWarnOverlay(QWidget):
    """自动化页 - CI运行警告浮层"""

    ciClosed = Signal()

    label_running_text = "ClassIsland 正在运行"
    label_running_desc = "<span style='font-size: 15px;'>需要关闭 ClassIsland 才能编辑自动化</span>"
    labelE_running_text = "唔，看起来 ClassIsland 还在运行呢"
    labelE_running_desc = (
        "<span style='font-size: 15px;'>这种坏事要偷偷地干啦，让 ClassIsland 大姐姐看到就不好了哦~</span>"
    )

    label_failed_text = "无法终止 ClassIsland"
    label_failed_desc = "<span style='font-size: 15px;'>自动关闭失败，请尝试手动关闭 ClassIsland</span>"
    labelE_failed_text = "诶诶，情况好像不太对？！"
    lalbelE_failed_desc = "<span style='font-size: 15px;'>没想到 ClassIsland 大姐姐竟然这么强势QAQ</span>"

    # NOTE: 改成浮层挪到右边后，给出的空间显示不下了……有机会再优化

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_container = QHBoxLayout()
        self.icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_icon = IconWidget()
        self.hint_icon.setFixedSize(96, 96)
        self.icon_container.addWidget(self.hint_icon)

        self.hint_label = TitleLabel()
        self.hint_desc = BodyLabel()
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action_button = PrimaryPushButton(icon=FluentIcon.POWER_BUTTON, text="终止 ClassIsland")
        self.action_button.clicked.connect(self.terminate_ci)

        layout.addLayout(self.icon_container)
        layout.addSpacing(12)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.hint_desc)
        layout.addSpacing(18)
        layout.addWidget(self.action_button)

        self.set_text()
        with contextlib.suppress(KeyError):
            SettingCard.index["App.EasterEggEnabled"].valueChanged.connect(lambda _: self.set_text())

    def set_text(self, failed: bool = False):
        if not failed:
            self.hint_icon.setIcon(FluentIcon.BROOM)
            if config.App.EasterEggEnabled:
                self.hint_label.setText(self.labelE_running_text)
                self.hint_desc.setText(self.labelE_running_desc)
            else:
                self.hint_label.setText(self.label_running_text)
                self.hint_desc.setText(self.label_running_desc)
                self.action_button.show()
        else:
            self.hint_icon.setIcon(FluentIcon.QUESTION)
            if config.App.EasterEggEnabled:
                self.hint_label.setText(self.labelE_failed_text)
                self.hint_desc.setText(self.labelE_failed_text)
            else:
                self.hint_label.setText(self.label_failed_text)
                self.hint_desc.setText(self.label_failed_desc)
            self.action_button.hide()

    def terminate_ci(self):
        if manager:
            logger.info("用户点击终止 ClassIsland")
            manager.close_ci()

    def mousePressEvent(self, event):
        event.accept()


class AutomationPage(QWidget):
    """设置 - 自动化页"""

    def __init__(self):
        super().__init__()
        logger.debug("初始化自动化页")
        self.setObjectName("AutomationPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        # 初始化 ClassIsland 管理器
        try:
            if config.ClassIsland.AutoPath:
                exe_path = utils.get_ci_executable()
            elif config.ClassIsland.Path:
                exe_path = Path(config.ClassIsland.Path)
            else:
                exe_path = None
        except Exception as e:
            logger.warning(f"获取 ClassIsland 路径失败: {e}")
            exe_path = None

        if exe_path and exe_path.exists():
            logger.debug(f"初始化 ClassIsland 管理器: {exe_path}")
            try:
                manager.initialize(exe_path)  # type: ignore (manager: _CiManagerProxy)
                logger.success("ClassIsland 管理器初始化成功")
            except Exception as e:
                logger.warning(f"ClassIsland 管理器初始化失败: {e}")
        else:
            logger.warning(f"{'未找到 ClassIsland 路径' if not exe_path else '路径无效'}，跳过初始化")

        self.init_ui()
        self.start_watcher()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.status_bar = AutomationStatusBar()

        # 主页面，下分管理页和路径选择页
        self.main_widget = QStackedWidget()

        self.path_select_page = PathSelectSubpage()
        self.manager_page = AutomationManageSubpage()

        self.main_widget.addWidget(self.path_select_page)
        self.main_widget.addWidget(self.manager_page)

        if manager:
            self.main_widget.setCurrentWidget(self.manager_page)

        self.path_select_page.pathChanged.connect(self.handle_path_changed)

        layout.addWidget(self.status_bar)
        layout.addWidget(HorizontalSeparator())
        layout.addWidget(self.main_widget)

    def start_watcher(self):
        """启动CI运行状态监听"""
        if not manager:
            logger.debug("管理器未初始化，跳过状态监听")
            return

        if hasattr(manager, "watcher"):
            logger.debug("状态监听已启动")
            return

        logger.info("启动 ClassIsland 状态监听")
        self.check_status()

        self.watcher = QTimer(self)
        self.watcher.timeout.connect(self.check_status)
        self.watcher.start(200)

    def check_status(self):
        """检查状态并切换页面"""
        target_page: QWidget
        if manager is None:
            target_page = self.path_select_page
        else:
            target_page = self.manager_page
            running = manager.is_ci_running
            if self.manager_page.overlay.isVisible() != running:
                self.status_bar.update_status()
                self.manager_page.set_ci_running_state(running)
                if not running:
                    self.manager_page._init_selector(reload=True)

        if self.main_widget.currentWidget() != target_page:
            logger.debug(f"切换自动化页面到: {target_page.__class__.__name__}")
            self.main_widget.setCurrentWidget(target_page)
            if target_page == self.manager_page:
                self.manager_page._init_selector(reload=True)
            self.status_bar.update_status()

    def handle_path_changed(self, path: Path):
        """重设 ClassIsland 管理器"""

        logger.info(f"尝试使用 {path} 初始化管理器")
        try:
            manager.initialize(path)  # type: ignore (manager: _CiManagerProxy)
            logger.success("ClassIsland 管理器初始化成功")
        except Exception as e:
            logger.error(f"ClassIsland 管理器初始化失败: {e}")
            InfoBar.error(
                title="错误",
                content="无法初始化管理器，请检查路径是否正确",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=get_main_container(),
            )
            return

        self.manager_page.init_manager()

        self.start_watcher()
