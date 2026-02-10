from __future__ import annotations

import contextlib
import sys
import time
import weakref
from enum import Enum
from pathlib import Path

import windows11toast
from loguru import logger

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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
    AvatarWidget,
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    CommandBar,
    DotInfoBadge,
    ExpandGroupSettingCard,
    FlowLayout,
    FluentIcon,
    FluentTranslator,
    HorizontalSeparator,
    HyperlinkCard,
    IconInfoBadge,
    IconWidget,
    ImageLabel,
    IndeterminateProgressBar,
    InfoBar,
    InfoBarPosition,
    InfoLevel,
    LineEdit,
    MessageBox,
    MessageBoxBase,
    MSFluentWindow,
    NavigationItemPosition,
    Pivot,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    PushSettingCard,
    SmoothScrollArea,
    SpinBox,
    SplashScreen,
    SubtitleLabel,
    SwitchButton,
    SystemThemeListener,
    Theme,
    TitleLabel,
    TransparentPushButton,
    VerticalSeparator,
    isDarkTheme,
    qconfig,
    setFont,
    setTheme,
    setThemeColor,
)

from EasiAuto import __version__, utils
from EasiAuto.ci_manager import EasiAutomation, manager
from EasiAuto.components import SettingCard
from EasiAuto.config import ConfigGroup, LoginMethod, UpdateMode, config
from EasiAuto.consts import EA_BASEDIR
from EasiAuto.qfw_widgets import ListWidget, SettingCardGroup
from EasiAuto.update import ChangeLog, UpdateDecision, update_checker
from EasiAuto.utils import get_resource


def set_enable_by(widgets: list[QWidget] | QWidget, switch: SwitchButton, reverse: bool = False):
    """通过开关启用组件"""
    widgets = [widgets] if isinstance(widgets, QWidget) else widgets

    def handle_check_change(checked: bool):
        for widget in widgets:
            is_enabled = checked if not reverse else not checked
            widget.setEnabled(is_enabled)
            if not is_enabled and isinstance(widget, ExpandGroupSettingCard):
                widget.setExpand(False)

    handle_check_change(switch.isChecked())
    switch.checkedChanged.connect(handle_check_change)


class ConfigPage(QWidget):
    """设置 - 配置页"""

    def __init__(self):
        super().__init__()
        logger.debug("初始化配置页")

        self.menu_index: weakref.WeakValueDictionary[str, SettingCardGroup] = weakref.WeakValueDictionary()

        self.init_ui()

    def init_ui(self):
        self.setObjectName("ConfigPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = TitleLabel("设置")
        title.setContentsMargins(36, 8, 0, 12)
        layout.addWidget(title)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.LeftMouseButtonGesture)
        layout.addWidget(self.scroll_area)

        # 创建内容容器
        self.content_widget = QWidget(self.scroll_area)
        self.scroll_area.setWidget(self.content_widget)

        # 内容布局
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(40, 0, 40, 20)
        self.content_layout.setSpacing(28)

        # 添加设置组
        for group in config.iter_items(exclude=["ClassIsland", "Update"]):
            self._add_config_menu(group)  # type: ignore
        self.apply_attachment()

        self.content_layout.addStretch()

    def _add_config_menu(self, config: ConfigGroup):
        """从配置生成设置菜单"""
        card_group = SettingCardGroup(config.title)
        card_group.setObjectName(config.name)
        self.menu_index[config.name] = card_group

        for item in config.children:
            card = SettingCard.from_config(item)

            card_group.addSettingCard(card)

        self.content_layout.addWidget(card_group)

    def apply_attachment(self):
        """应用附加的界面样式与属性"""

        # 额外设置项

        # for name, menu in self.menu_index.items():
        #     match name:
        #         case "":
        #             ...
        # 目前无需插入到已有菜单中，注释以备用

        reset_card = PushSettingCard(
            text="重置",
            icon=FluentIcon.CANCEL,
            title="重置配置",
            content="将所有配置项重置为默认值",
        )
        reset_card.clicked.connect(self.reset_config)
        self.content_layout.addWidget(reset_card)

        # 开发选项
        collapse_card = PushSettingCard(
            icon=FluentIcon.DEVELOPER_TOOLS,
            title="崩溃测试",
            text="崩溃",
        )

        collapse_card.clicked.connect(utils.crash)
        self.content_layout.addWidget(collapse_card)
        collapse_card.setVisible(config.App.DebugMode)

        # 额外属性
        for name, card in SettingCard.index.items():
            match name:
                case "Login.Method":
                    card.widget.setMinimumWidth(180)
                    # 暂时禁用固定位置
                    fixed_index = card.widget.findData(LoginMethod.FIXED_POSITION)
                    if fixed_index != -1:
                        card.widget.setItemEnabled(fixed_index, False)
                case "Login.SkipOnce":
                    button_card = TransparentPushButton(icon=FluentIcon.SHARE, text="创建快捷方式")
                    button_card.clicked.connect(
                        lambda: utils.create_shortcut(
                            args="skip",
                            name="跳过下次自动登录",
                            show_result_to=MainWindow.container,
                        )
                    )
                    card.hBoxLayout.insertWidget(5, button_card)
                    card.hBoxLayout.insertSpacing(6, 12)
                case "Login.EasiNote":
                    self.add_resetter(card, "Login.EasiNote", "希沃白板选项")  # type: ignore
                case (
                    "Login.EasiNote.Path"
                    | "Login.EasiNote.ProcessName"
                    | "Login.EasiNote.WindowTitle"
                    | "Login.EasiNote.Args"
                ):
                    card.widget.setFixedWidth(400)
                case "Login.Timeout":
                    self.add_resetter(card, "Login.Timeout", "超时时长")  # type: ignore
                case n if n.startswith("Login.Timeout."):
                    card.widget.setMinimumWidth(160)
                case "Login.Position":
                    recoard_card = PushSettingCard(
                        icon=FluentIcon.CAMERA, title="录制模式", content="进入录制模式获取坐标", text="录制"
                    )
                    recoard_card.button.setEnabled(False)
                    # button.clicked.connect() # TODO: 录制模式
                    self.add_resetter(card, "Login.Position", "位置坐标")  # type: ignore
                case "Banner.Style":
                    self.add_resetter(card, "Banner.Style", "横幅样式")  # type: ignore
                case "Banner.Style.Text":
                    card.widget.setFixedWidth(420)
                case "Banner.Style.TextFont":
                    card.widget.setFixedWidth(200)
                    card.widget.setClearButtonEnabled(True)
                case "App.LogLevel":
                    card.widget.setMinimumWidth(104)

        # 从属关系
        set_enable_by(
            SettingCard.index["Login.EasiNote.Path"],
            SettingCard.index["Login.EasiNote.AutoPath"].widget,  # type: ignore
        )
        set_enable_by(
            [
                SettingCard.index["Warning.Timeout"],
                SettingCard.index["Warning.MaxDelays"],
                SettingCard.index["Warning.DelayTime"],
            ],
            SettingCard.index["Warning.Enabled"].widget,  # type: ignore
        )
        set_enable_by(SettingCard.index["Banner.Style"], SettingCard.index["Banner.Enabled"].widget)  # type: ignore

        # 值变化事件
        SettingCard.index["App.Theme"].valueChanged.connect(lambda t: setTheme(Theme(t.value)))

    def add_resetter(self, parent: ExpandGroupSettingCard, path: str, display_name: str = "设置"):
        reset_card = PushSettingCard(
            icon=FluentIcon.CANCEL,
            title=f"重置{display_name}",
            content=f"将所有{display_name}重置为默认值",
            text="重置",
        )
        reset_card.clicked.connect(lambda: self.reset_settings_by_path(path, display_name))
        parent.addGroupWidget(reset_card)

    def reset_settings_by_path(self, path: str, display_name: str = "设置"):
        config.reset_by_path(path)
        SettingCard.update_all()

        # 弹出提示
        InfoBar.success(
            title="成功",
            content=f"{display_name}已重置",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=MainWindow.container,
        )

    def reset_config(self):
        """重置配置为默认值"""
        title = "确认要重置配置吗？"
        content = "所有已编辑的设置将丢失，是否继续？"
        w = MessageBox(title, content, self)

        w.setClosableOnMaskClicked(True)

        if w.exec():
            # 重置设置
            config.reset_all()
            SettingCard.update_all()

            # 弹出提示
            InfoBar.success(
                title="成功",
                content="设置已重置",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=MainWindow.container,
            )


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
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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
        info_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

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
        self.command_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

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
        if e.button() == Qt.LeftButton:
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
        self.action_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
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
        QScroller.grabGesture(self.auto_list.viewport(), QScroller.LeftMouseButtonGesture)

        self.selector_layout.addWidget(self.action_bar)
        self.selector_layout.addWidget(self.auto_list)

        # 右侧：容器 (包含编辑器和浮层)
        self.right_container = QWidget()
        self.right_layout = QStackedLayout(self.right_container)
        self.right_layout.setStackingMode(QStackedLayout.StackAll)

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
        item.setData(Qt.UserRole, automation)

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
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=MainWindow.container,
            )

    def _on_item_clicked(self, item: QListWidgetItem):
        """列表项点击事件"""
        automation = item.data(Qt.UserRole)
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

        from EasiAuto.automator import CVAutomator, FixedAutomator, UIAAutomator
        from EasiAuto.components import WarningBanner

        # 最小化设置界面
        main_window = app.activeWindow()
        if main_window:
            main_window.showMinimized()

        # NOTE: 下方运行逻辑在 main.py cmd_login() 中存在相同实现，如更改需同步替换

        # 显示警示横幅
        if config.Banner.Enabled:
            try:
                screen = app.primaryScreen().geometry()
                self.banner = WarningBanner(config.Banner.Style)
                self.banner.setGeometry(0, 80, screen.width(), 140)  # 顶部横幅
                self.banner.show()
            except Exception:
                logger.error("显示横幅时出错，跳过横幅")

        # 执行登录
        logger.debug(f"当前设置的登录方案: {config.Login.Method}")
        match config.Login.Method:  # 选择登录方案
            case LoginMethod.UI_AUTOMATION:
                automator_type = UIAAutomator
            case LoginMethod.OPENCV:
                automator_type = CVAutomator
            case LoginMethod.FIXED_POSITION:
                automator_type = FixedAutomator

        self.automator = automator_type(automation.account, automation.password, config.Login, config.App.MaxRetries)

        self.automator.start()
        self.automator.finished.connect(self._clean_up_after_run)

    def _clean_up_after_run(self, message: str):
        """清理运行后的资源"""
        if hasattr(self, "banner"):
            self.banner.close()
            del self.banner

        # 根据返回消息弹出提示
        if "失败" in message:
            InfoBar.error(
                title="自动登录失败",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=MainWindow.container,
            )
        else:
            InfoBar.success(
                title="成功",
                content="自动登录已完成",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=MainWindow.container,
            )

        self.automator.terminate()  # 保险起见 双重退出
        logger.success(f"自动化运行结束: {message}")

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
            show_result_to=MainWindow.container,
        )

    def _handle_action_remove(self, item: QListWidgetItem):
        """操作 - 删除自动化"""
        if not manager:
            logger.warning("无法删除自动化: 管理器未初始化")
            return

        automation = item.data(Qt.UserRole)
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
            if item.data(Qt.UserRole).guid == guid:
                # 更新 item 数据
                item.setData(Qt.UserRole, automation)
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
            if item.data(Qt.UserRole).guid == guid:
                # 如果删除的是当前项，清空编辑器
                if self.current_list_item == item:
                    self.current_list_item = None
                    self._clear_editor()
                automation_name = item.data(Qt.UserRole).item_display_name
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
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=MainWindow.container,
            )
            config.ClassIsland.AutoPath = False
            config.ClassIsland.Path = str(exe_path)
            self.pathChanged.emit(exe_path)
        else:
            logger.error("选择的路径不存在")
            InfoBar.error(
                title="错误",
                content="选择的路径不存在",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=MainWindow.container,
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
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=MainWindow.container,
            )
            return

        self.manager_page.init_manager()

        self.start_watcher()


class HighlightedChangeLogCard(CardWidget):
    def __init__(self, name: str, description: str):
        super().__init__()

        self.setFixedSize(256, 120)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)

        name_label = SubtitleLabel(name)  # ! 最多 11 个字
        changelog_label = BodyLabel(description)  # ! 最多 16*3 个字
        name_label.setWordWrap(True)
        changelog_label.setWordWrap(True)

        layout.addWidget(name_label)
        layout.addWidget(changelog_label)


class UpdateContentView(QWidget):
    def __init__(self, change_log: ChangeLog | None = None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 0, 30, 0)
        layout.setSpacing(2)

        self.pivot = Pivot()
        self.stacked_widget = QStackedWidget()

        self.change_log_container = self._init_change_log_interface()
        self.settings_container = self._init_update_settings()

        self.addSubInterface(self.change_log_container, "changeLogContainer", "更新日志")
        self.addSubInterface(self.settings_container, "settingsContainer", "更新设置")

        # qfluentwidgets 的 PivotItem 字号高达 18，丑爆了……
        for item in self.pivot.items.values():
            setFont(item, 15)

        self.stacked_widget.currentChanged.connect(self.onCurrentIndexChanged)
        self.stacked_widget.setCurrentWidget(self.change_log_container)
        self.pivot.setCurrentItem(self.change_log_container.objectName())

        layout.addWidget(self.pivot, 0, Qt.AlignLeft)
        layout.addWidget(self.stacked_widget)

    def _init_change_log_interface(self):
        container = QWidget()

        scroll_layout = QVBoxLayout(container)

        self.description_label = BodyLabel()

        self.highlights_title = SubtitleLabel("✨ 亮点")
        self.highlights_layout = FlowLayout()

        self.others_title = SubtitleLabel("📃 其他")
        self.others_layout = QVBoxLayout()

        self.placeholder_label = BodyLabel("暂无日志")
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setWordWrap(True)

        scroll_layout.addWidget(self.placeholder_label)
        scroll_layout.addWidget(self.description_label)
        scroll_layout.addSpacing(10)
        scroll_layout.addWidget(self.highlights_title)
        scroll_layout.addLayout(self.highlights_layout)
        scroll_layout.addSpacing(20)
        scroll_layout.addWidget(self.others_title)
        scroll_layout.addLayout(self.others_layout)
        scroll_layout.addStretch(1)

        # Make it scrollable!
        scroll_area = SmoothScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        QScroller.grabGesture(scroll_area.viewport(), QScroller.LeftMouseButtonGesture)
        scroll_area.setWidget(container)

        return scroll_area

    def _init_update_settings(self):
        container = QWidget()
        scroll_layout = QVBoxLayout(container)
        scroll_layout.setSpacing(2)

        for item in config.iter_items(only=["Update"])[0].children:
            scroll_layout.addWidget(SettingCard.from_config(item))

        reset_card = PushSettingCard(
            text="强制检查",
            icon=FluentIcon.ASTERISK,
            title="强制检查更新",
            content="强制将应用更新到当前通道及分支上的最新版本，可以通过这种方式切换分支",
        )
        reset_card.clicked.connect(lambda: update_checker.check_async(force=True))
        scroll_layout.addWidget(reset_card)

        scroll_layout.addStretch(1)

        # Make it scrollable again!
        scroll_area = SmoothScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        QScroller.grabGesture(scroll_area.viewport(), QScroller.LeftMouseButtonGesture)
        scroll_area.setWidget(container)

        return scroll_area

    def set_change_log(self, change_log: ChangeLog | None):
        """允许初始化后传入/更新 changelog。"""
        self.description_label.setText("")
        self.highlights_layout.takeAllWidgets()
        while self.others_layout.count():
            w = self.others_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        self.placeholder_label.setVisible(not bool(change_log))
        self.description_label.setVisible(bool(getattr(change_log, "description", None)))
        self.highlights_title.setVisible(bool(getattr(change_log, "highlights", None)))
        self.others_title.setVisible(bool(getattr(change_log, "others", None)))

        if not change_log:
            return

        try:
            self.description_label.setText(change_log.description)

            for item in change_log.highlights:
                card = HighlightedChangeLogCard(item["name"], item["description"])
                self.highlights_layout.addWidget(card)

            for desc in change_log.others:
                label = BodyLabel(f"• {desc}")
                label.setWordWrap(True)
                self.others_layout.addWidget(label)
        except Exception as e:
            logger.warning(f"显示更新日志时发生错误：{e}")
            self.placeholder_label.setVisible(True)
            self.highlights_title.setVisible(False)
            self.others_title.setVisible(False)

    def addSubInterface(self, widget: QWidget, object_name: str, text: str):
        widget.setObjectName(object_name)

        self.stacked_widget.addWidget(widget)
        self.pivot.addItem(
            routeKey=object_name,
            text=text,
            onClick=lambda: self.stacked_widget.setCurrentWidget(widget),
        )

    def onCurrentIndexChanged(self, index):
        widget = self.stacked_widget.widget(index)
        self.pivot.setCurrentItem(widget.objectName())


class UpdateStatus(Enum):
    FAILED = "failed"
    CHECK = "check"
    CHECKING = "checking"
    DOWNLOAD = "download"
    DOWNLOADING = "downloading"
    DOWNLOAD_CANCELED = "downloadCanceled"
    INSTALL = "install"


class UpdatePage(QWidget):
    def __init__(self):
        super().__init__()
        logger.debug("初始化更新页")
        self.setObjectName("UpdatePage")
        self.setStyleSheet("border: none; background-color: transparent;")

        update_checker.check_started.connect(self.check_started)
        update_checker.check_finished.connect(self.check_finished)
        update_checker.check_failed.connect(self.check_failed)

        update_checker.download_started.connect(self.download_started)
        update_checker.download_progress.connect(self.download_progress)
        update_checker.download_finished.connect(self.download_finished)
        update_checker.download_failed.connect(self.download_failed)

        self._action: UpdateStatus
        self._decision: UpdateDecision | None = None
        self._update_file: str = "EasiAuto_Unknown.zip"
        self._last_check: str | None = None
        self._last_error: str | None = None
        self._signal_connected: bool = False
        self._tried_downloads: int = 0

        self.init_ui()
        self.action = UpdateStatus.CHECK
        if config.Update.Mode.value > UpdateMode.NEVER.value:
            update_checker.check_async()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = TitleLabel("更新")
        title.setContentsMargins(36, 8, 0, 12)
        layout.addWidget(title)

        status_widget = QWidget()
        status_widget.setFixedHeight(96)
        status_widget.setContentsMargins(36, 0, 36, 0)
        status_layout = QHBoxLayout(status_widget)

        icon = IconWidget(FluentIcon.SYNC)
        icon.setFixedSize(48, 48)
        text_layout = QVBoxLayout()
        text_layout.setAlignment(Qt.AlignTop)
        self.title = SubtitleLabel()
        font = self.title.font()
        font.setPixelSize(24)
        self.title.setFont(font)
        self.detail = BodyLabel()
        self.progress_bar = IndeterminateProgressBar()
        self.progress_bar.hide()
        self.download_progress_bar = ProgressBar()
        self.download_progress_bar.setRange(0, 100)
        self.download_progress_bar.hide()
        self.action_button = PrimaryPushButton()
        self.action_button.clicked.connect(self.handle_button_action)

        status_layout.addWidget(icon)
        status_layout.addSpacing(8)
        text_layout.addWidget(self.title)
        text_layout.addSpacing(3)
        text_layout.addWidget(self.detail)
        text_layout.addWidget(self.progress_bar)
        text_layout.addWidget(self.download_progress_bar)
        status_layout.addLayout(text_layout)
        status_layout.addSpacing(8)
        status_layout.addWidget(self.action_button, alignment=Qt.AlignRight)

        self.content_widget = UpdateContentView()

        layout.addWidget(status_widget)
        layout.addWidget(HorizontalSeparator())
        layout.addWidget(self.content_widget)

    @property
    def action(
        self,
    ) -> UpdateStatus:
        return self._action

    @action.setter
    def action(self, new: UpdateStatus):
        """更新状态管理"""
        self._action = new

        self.title.setText("TITLE")
        self.detail.hide()
        self.detail.setText("DETAIL")
        self.progress_bar.hide()
        self.download_progress_bar.hide()
        self.action_button.setEnabled(True)
        self.action_button.setText("ACTION")

        match new:
            case UpdateStatus.CHECK:
                self.title.setText("你使用的是最新版本")
                self.detail.show()
                self.detail.setText(f"上次检查时间：{self._last_check or '暂未检查'}")
                self.action_button.setText("检查更新")
                self.content_widget.set_change_log(None)
            case UpdateStatus.CHECKING:
                self.title.setText("正在检查更新……")
                self.progress_bar.show()
                self.action_button.setText("检查更新")
                self.action_button.setEnabled(False)
            case UpdateStatus.DOWNLOAD:
                if not self._decision:
                    self._last_error = "无可用更新"
                    self.action = UpdateStatus.FAILED
                    return
                logger.info(
                    f"更新可用：{self._decision.target_version}"
                    if not self._decision.confirm_required
                    else f"需要确认的更新：{self._decision.target_version}"
                )
                self.title.setText(
                    f"更新可用：{self._decision.target_version}"
                    if not self._decision.confirm_required
                    else f"需要确认的更新：{self._decision.target_version}"
                )
                windows11toast.notify(
                    title="更新可用" if not self._decision.confirm_required else "存在需要确认的更新",
                    body=f"新版本：{self._decision.target_version}\n打开应用查看详细信息",
                    icon_placement=windows11toast.IconPlacement.APP_LOGO_OVERRIDE,
                    icon_hint_crop=windows11toast.IconCrop.NONE,
                    icon_src=utils.get_resource("EasiAuto.ico"),
                )
                self.detail.show()
                self.detail.setText(f"上次检查时间：{self._last_check or '暂未检查'}")
                self.action_button.setText("下载")
                self.content_widget.set_change_log(self._decision.change_log)
                if (
                    config.Update.Mode.value >= UpdateMode.CHECK_AND_DOWNLOAD.value
                    and not self._decision.confirm_required
                ):
                    update_checker.download_async(self._decision.downloads[0], filename=self._update_file)
            case UpdateStatus.DOWNLOADING:
                logger.info("正在下载更新")
                self.title.setText("正在下载更新……")
                self.download_progress_bar.show()
                self.action_button.setText("取消")
            case UpdateStatus.DOWNLOAD_CANCELED:
                if not self._decision:
                    self._last_error = "无可用更新"
                    self.action = UpdateStatus.FAILED
                    return
                self.title.setText(f"更新可用：{self._decision.target_version}")
                self.detail.show()
                self.detail.setText(
                    "若多次尝试后仍下载缓慢或无法下载，可启用镜像下载源"
                    if self._tried_downloads >= 2
                    else f"上次检查时间：{self._last_check or '暂未检查'}"
                )
                self.action_button.setText("下载")
            case UpdateStatus.INSTALL:
                logger.success("更新已就绪")
                self.title.setText("更新已就绪")
                self.detail.show()
                if config.Update.Mode.value >= UpdateMode.CHECK_AND_INSTALL.value:
                    app.aboutToQuit.connect(
                        lambda: update_checker.apply_script(zip_path=EA_BASEDIR / "cache" / self._update_file),
                    )
                    self._signal_connected = True
                    self.detail.setText("应用退出后将自动应用更新，或者你也可以现在重启以应用更新")
                else:
                    self.detail.setText("需要手动确认以应用更新")
                self.action_button.setText("重启并应用更新")

            case UpdateStatus.FAILED:
                logger.error("检查更新时发生错误")
                self.title.setText("发生错误")
                self.detail.show()
                if self._last_error:
                    self.detail.setText(f"错误信息：{self._last_error}")
                    self._last_error = None
                else:
                    self.detail.setText("未知错误，请重试或向开发者报告问题")
                self.action_button.setText("重试")

    # NOTE: 上下部分逻辑重合，需要同步修改

    def handle_button_action(self):
        """响应更新各步骤的操作"""
        match self.action:
            case UpdateStatus.CHECK | UpdateStatus.FAILED:
                update_checker.check_async()
            case UpdateStatus.DOWNLOAD | UpdateStatus.DOWNLOAD_CANCELED:
                if not self._decision:
                    self._last_error = "无可用更新"
                    self.action = UpdateStatus.FAILED
                    return
                update_checker.download_async(self._decision.downloads[0], filename=self._update_file)
            case UpdateStatus.DOWNLOADING:  # 取消下载
                update_checker.cancel_download()
            case UpdateStatus.INSTALL:
                if not self._signal_connected:
                    app.aboutToQuit.connect(
                        lambda: update_checker.apply_script(zip_path=EA_BASEDIR / "cache" / self._update_file),
                    )
                utils.stop()

    def check_started(self):
        self.action = UpdateStatus.CHECKING

    def check_finished(self, decision: UpdateDecision):
        self._last_check = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        if decision.available and len(decision.downloads) > 0:
            self._decision = decision
            self._update_file = f"EasiAuto_{decision.target_version or 'Unknown'}.zip"
            self.action = UpdateStatus.DOWNLOAD
        else:
            self.action = UpdateStatus.CHECK

    def check_failed(self, error: str):
        self._last_error = error
        self.action = UpdateStatus.FAILED

    def download_started(self):
        self.action = UpdateStatus.DOWNLOADING

    def download_progress(self, downloaded, total):
        self.download_progress_bar.setValue(round(100 * downloaded / total))

    def download_finished(self):
        self.action = UpdateStatus.INSTALL

    def download_failed(self, error):
        if "取消" in error:
            self.download_progress_bar.setValue(0)
            self.action = UpdateStatus.DOWNLOAD_CANCELED
        else:
            self._last_error = error
            self.action = UpdateStatus.FAILED


class AboutPage(SmoothScrollArea):
    """设置 - 关于页"""

    def __init__(self):
        super().__init__()
        logger.debug("初始化关于页")
        self.setObjectName("AboutPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = TitleLabel("关于")
        title.setContentsMargins(36, 8, 0, 12)
        layout.addWidget(title)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.LeftMouseButtonGesture)
        layout.addWidget(self.scroll_area)

        # 居中容器
        self.scroll_container = QWidget()
        self.scroll_area.setWidget(self.scroll_container)

        self.scroll_container_layout = QHBoxLayout(self.scroll_container)
        self.scroll_container_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_container_layout.setAlignment(Qt.AlignHCenter)

        self.content_widget = QWidget()
        self.content_widget.setMaximumWidth(600)
        self.scroll_container_layout.addWidget(self.content_widget)

        # 内容容器
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 20)
        self.content_layout.setSpacing(28)

        # 产品信息卡片
        self.banner_container = CardWidget()
        banner_container_layout = QVBoxLayout(self.banner_container)
        banner_container_layout.setContentsMargins(0, 0, 0, 0)
        banner_container_layout.setAlignment(Qt.AlignTop)

        # 主视觉图
        _banner_img_src = QPixmap(get_resource("banner.png"))
        banner_image = ImageLabel(_banner_img_src)
        banner_image.setFixedWidth(600)
        banner_image.scaledToWidth(600)
        banner_image.setBorderRadius(8, 8, 0, 0)
        banner_container_layout.addWidget(banner_image)

        banner_layout = QVBoxLayout()
        banner_layout.setAlignment(Qt.AlignTop)
        banner_layout.setContentsMargins(20, 0, 20, 12)
        banner_layout.setSpacing(16)

        # 应用描述
        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignBottom)
        title = TitleLabel("EasiAuto", self)
        subtitle = SubtitleLabel(f"版本 {__version__}", self)
        title_layout.addWidget(title)
        title_layout.addSpacing(6)
        title_layout.addWidget(subtitle)
        title_layout.addStretch(1)

        banner_layout.addLayout(title_layout)

        description_layout = QVBoxLayout()
        product_text = BodyLabel("一款自动登录希沃白板的小工具")
        github_link = HyperlinkCard(
            icon=FluentIcon.GITHUB,
            title="GitHub 仓库",
            content="不妨点个 Star 支持一下？  (≧∇≦)ﾉ★",
            url="https://github.com/hxabcd/EasiAuto",
            text="查看",
        )
        additional_info = ExpandGroupSettingCard(
            icon=FluentIcon.INFO, title="其他信息", content="开源协议、第三方库、鸣谢"
        )
        additional_info.viewLayout.setContentsMargins(16, 8, 16, 12)
        additional_info.viewLayout.setSpacing(6)
        additional_info.addGroupWidget(BodyLabel("本项自基于 GNU General Public License v3.0 (GPLv3) 获得许可"))
        additional_info.addGroupWidget(
            BodyLabel(
                "\n  - ".join(
                    [
                        "本项目使用到的第三方库（仅列出部分）：",
                        "qfluentwidget",
                        "PySide6",
                        "Pydantic",
                        "pywinauto",
                        "pyautogui",
                        "loguru",
                    ]
                )
            )
        )
        additional_info.addGroupWidget(
            BodyLabel(
                "\n  - ".join(
                    [
                        "特别感谢：",
                        "智教联盟 对本项目的宣传",
                        "Class-Widget 对本项目代码提供参考",
                        "ClassIsland 「自动化」 对本项目提供载体",
                        "我的初中英语老师 为本项目提供动机",
                    ]
                )
                + "\n\n    以及——愿意使用 EasiAuto 的你"
            )
        )
        description_layout.addWidget(product_text)
        description_layout.addWidget(github_link)
        description_layout.addWidget(additional_info)  # NOTE: 不知道为什么折叠的时候会抽搐，之后再修吧
        banner_layout.addLayout(description_layout)

        banner_container_layout.addLayout(banner_layout)
        self.content_layout.addWidget(self.banner_container)

        # 作者信息卡片
        self.author_area = CardWidget()
        author_layout = QVBoxLayout(self.author_area)
        author_layout.setAlignment(Qt.AlignTop)
        author_layout.setContentsMargins(24, 16, 24, 16)

        author_info_layout = QHBoxLayout()

        author_avatar = AvatarWidget(QPixmap(get_resource("author_avatar.jpg")))
        author_avatar.setRadius(24)

        sub_layout = QVBoxLayout()
        sub_layout.setSpacing(0)
        author_name = SubtitleLabel("HxAbCd")
        author_content = CaptionLabel("Just be yourself.")
        author_content.setTextColor(QColor("#878787"), QColor("#b5b5b5"))
        sub_layout.addWidget(author_name)
        sub_layout.addWidget(author_content)

        author_info_layout.addWidget(author_avatar)
        author_info_layout.addSpacing(4)
        author_info_layout.addLayout(sub_layout)
        author_info_layout.addStretch(1)

        author_link1 = HyperlinkCard(
            icon=FluentIcon.GLOBE,
            title="个人网站",
            url="https://0xabcd.dev",
            text="访问",
        )
        author_link2 = HyperlinkCard(
            icon=FluentIcon.HOME_FILL,
            title="哔哩哔哩主页",
            url="https://space.bilibili.com/401002238",
            text="访问",
        )
        author_link3 = HyperlinkCard(
            icon=FluentIcon.GITHUB,
            title="Github 主页",
            url="https://github.com/hxabcd",
            text="访问",
        )

        author_layout.addLayout(author_info_layout)
        author_layout.addSpacing(4)
        author_layout.addWidget(author_link1)
        author_layout.addWidget(author_link2)
        author_layout.addWidget(author_link3)

        self.content_layout.addWidget(self.author_area)
        self.content_layout.addStretch(1)


class MainWindow(MSFluentWindow):
    container: QWidget | None = None

    def __init__(self):
        logger.debug("初始化界面")
        super().__init__()
        self.initWindow()

        # 启动页面
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(102, 102))
        logger.debug("显示启动页面")
        self.show()

        self.config_page = ConfigPage()
        self.automation_page = AutomationPage()
        self.update_page = UpdatePage()
        self.about_page = AboutPage()
        self.initNavigation()

        self.themeListener.start()

        logger.success("界面初始化完成")
        self.splashScreen.finish()
        MainWindow.container = self.stackedWidget

    def initNavigation(self):
        self.addSubInterface(self.config_page, FluentIcon.SETTING, "配置")
        self.addSubInterface(self.automation_page, FluentIcon.AIRPLANE, "自动化")
        self.addSubInterface(self.update_page, FluentIcon.UPDATE, "更新")
        self.addSubInterface(
            self.about_page,
            FluentIcon.INFO,
            "关于",
            position=NavigationItemPosition.BOTTOM,
        )

    def initWindow(self):
        self.setWindowIcon(QIcon(get_resource("EasiAuto.ico")))
        self.setWindowTitle("EasiAuto")
        self.setMinimumSize(800, 500)
        self.resize(960, 640)

        self.themeListener = SystemThemeListener(self)
        qconfig.themeChanged.connect(setTheme)

    def closeEvent(self, e):
        self.themeListener.terminate()  # 停止监听器线程
        super().closeEvent(e)

    def _onThemeChangedFinished(self):
        super()._onThemeChangedFinished()

        # 云母特效启用时需要增加重试机制
        if self.isMicaEffectEnabled():
            QTimer.singleShot(100, lambda: self.windowEffect.setMicaEffect(self.winId(), isDarkTheme()))


# os.environ['QT_SCALE_FACTOR'] = ...

app = QApplication(sys.argv)
translator = FluentTranslator()
app.installTranslator(translator)
setTheme(Theme(config.App.Theme.value))
setThemeColor("#00C884")
