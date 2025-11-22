import logging
import sys
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidgetItem,
    QScroller,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CardWidget,
    ComboBox,
    ComboBoxSettingCard,
    CommandBar,
    DotInfoBadge,
    ExpandGroupSettingCard,
    ExpandSettingCard,
    FluentTranslator,
    FluentWindow,
    HyperlinkLabel,
    Icon,
    IconInfoBadge,
    ImageLabel,
    InfoBar,
    InfoBarPosition,
    InfoLevel,
    LineEdit,
    MessageBox,
    NavigationItemPosition,
    PrimaryPushButton,
    PushButton,
    PushSettingCard,
    SettingCardGroup,
    SmoothScrollArea,
    SpinBox,
    StrongBodyLabel,
    SubtitleLabel,
    SwitchButton,
    Theme,
    TitleLabel,
    TransparentPushButton,
    qconfig,
    setTheme,
)
from qfluentwidgets import FluentIcon as FIF

from ci_automation_manager import CiAutomationManager, EasiAutomation
from components import (
    ColorSettingCard,
    EditSettingCard,
    ListWidget,
    RangeSettingCard,
    Separator,
    SpinSettingCard,
    SwitchSettingCard,
)
from config import QfwEasiautoConfig
from utils import create_script, get_ci_executable_path, get_executable, get_executable_path, get_resource


class EasinoteSettingCard(ExpandGroupSettingCard):
    def __init__(self, config: QfwEasiautoConfig, parent=None):
        super().__init__(FIF.APPLICATION, "希沃白板", "配置希沃白板的路径、进程名、窗口标题和启动参数", parent)

        self.autoPathSwitch = SwitchSettingCard(
            None, "自动获取路径", "启用后，将忽略自定义路径", configItem=config.easinoteAutoPath, is_item=True
        )

        self.pathEdit = EditSettingCard(None, "自定义路径", configItem=config.easinotePath, is_item=True)
        self.pathEdit.lineEdit.setFixedWidth(400)

        set_enable_by(self.autoPathSwitch.switchButton, self.pathEdit, reverse=True)

        self.processNameEdit = EditSettingCard(None, "进程名", configItem=config.easinoteProcessName, is_item=True)
        self.processNameEdit.lineEdit.setFixedWidth(400)

        self.windowTitleEdit = EditSettingCard(None, "窗口标题", configItem=config.easinoteWindowTitle, is_item=True)
        self.windowTitleEdit.lineEdit.setFixedWidth(400)

        self.argsEdit = EditSettingCard(None, "参数", configItem=config.easinoteArgs, is_item=True)
        self.argsEdit.lineEdit.setClearButtonEnabled(True)
        self.argsEdit.lineEdit.setFixedWidth(400)

        # 调整内部布局
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.setSpacing(0)

        # 添加各组到设置卡中
        self.addGroupWidget(self.autoPathSwitch)
        self.addGroupWidget(self.pathEdit)
        self.addGroupWidget(self.processNameEdit)
        self.addGroupWidget(self.windowTitleEdit)
        self.addGroupWidget(self.argsEdit)


class TimeoutSettingCard(ExpandGroupSettingCard):
    def __init__(self, config: QfwEasiautoConfig, parent=None):
        super().__init__(FIF.STOP_WATCH, "等待时长", "配置自动登录过程中的等待时长", parent)

        self.pathEdit = SpinSettingCard(
            None, "终止进程等待时间", configItem=config.timeoutTerminate, min_width=160, is_item=True
        )
        self.launchPollingTimeoutEdit = SpinSettingCard(
            None, "等待启动超时时间", configItem=config.timeoutLaunchPollingTimeout, min_width=160, is_item=True
        )
        self.launchPollingIntervalEdit = SpinSettingCard(
            None,
            "等待启动轮询间隔",
            configItem=config.timeoutLaunchPollingInterval,
            double=True,
            min_width=160,
            is_item=True,
        )
        self.afterLaunchEdit = SpinSettingCard(
            None, "启动后等待时间", configItem=config.timeoutAfterLaunch, min_width=160, is_item=True
        )
        self.enterLoginUiEdit = SpinSettingCard(
            None, "进入登录界面等待时间", configItem=config.timeoutEnterLoginUI, min_width=160, is_item=True
        )
        self.switchTabEdit = SpinSettingCard(
            None, "切换标签等待时间", configItem=config.timeoutSwitchTab, min_width=160, is_item=True
        )

        # 调整内部布局
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.setSpacing(0)

        # 添加各组到设置卡中
        self.addGroupWidget(self.pathEdit)
        self.addGroupWidget(self.launchPollingTimeoutEdit)
        self.addGroupWidget(self.launchPollingIntervalEdit)
        self.addGroupWidget(self.afterLaunchEdit)
        self.addGroupWidget(self.enterLoginUiEdit)
        self.addGroupWidget(self.switchTabEdit)


class BannerStyleSettingCard(ExpandGroupSettingCard):
    def __init__(self, config: QfwEasiautoConfig, parent=None):
        super().__init__(FIF.BRUSH, "横幅样式", "定制警示横幅的样式与外观", parent)

        self.banner_text_edit = EditSettingCard(
            icon=None,
            title="文本",
            content="设置警示横幅中滚动的文本内容",
            configItem=config.bannerText,
            is_item=True,
        )
        self.banner_text_edit.lineEdit.setFixedWidth(420)

        self.text_font_edit = EditSettingCard(
            icon=None,
            title="文本字体",
            content="设置警示横幅的文本字体",
            configItem=config.bannerTextFont,
            placeholder_text="输入字体名称",
            is_item=True,
        )
        self.text_font_edit.lineEdit.setClearButtonEnabled(True)
        self.text_font_edit.lineEdit.setMinimumWidth(200)

        self.text_color_edit = ColorSettingCard(
            icon=None,
            title="文本颜色",
            content="设置警示横幅的文本颜色",
            configItem=config.bannerTextColor,
            enableAlpha=True,
            is_item=True,
        )

        self.bg_color_edit = ColorSettingCard(
            icon=None,
            title="背景颜色",
            content="设置警示横幅的背景颜色",
            configItem=config.bannerBgColor,
            enableAlpha=True,
            is_item=True,
        )

        self.fg_color_edit = ColorSettingCard(
            icon=None,
            title="前景颜色",
            content="设置警示横幅的前景颜色",
            configItem=config.bannerFgColor,
            enableAlpha=True,
            is_item=True,
        )

        self.fps_edit = RangeSettingCard(
            icon=None,
            title="帧率",
            content="设置警示横幅的刷新帧率",
            configItem=config.bannerFps,
            is_item=True,
        )

        self.text_speed_edit = RangeSettingCard(
            icon=None,
            title="文本速度",
            content="设置警示横幅中文本的滚动速度，增大以抵消低帧率下滚动缓慢",
            configItem=config.bannerTextSpeed,
            is_item=True,
        )

        # 调整内部布局
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.setSpacing(0)

        # 添加各组到设置卡中
        self.addGroupWidget(self.banner_text_edit)
        self.addGroupWidget(self.text_font_edit)
        self.addGroupWidget(self.text_color_edit)
        self.addGroupWidget(self.bg_color_edit)
        self.addGroupWidget(self.fg_color_edit)
        self.addGroupWidget(self.fps_edit)
        self.addGroupWidget(self.text_speed_edit)


class ConfigPage(SmoothScrollArea):
    """设置 - 配置页"""

    def __init__(self):
        super().__init__()

        config_file = get_executable_path() / "config.json"
        self.config = QfwEasiautoConfig()
        qconfig.load(config_file, self.config)

        self.init_ui()

    def init_ui(self):
        logging.debug("初始化 ConfigPage UI")
        self.setObjectName("ConfigPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        # 创建滚动区域
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMinimumSize(750, 480)
        QScroller.grabGesture(self.viewport(), QScroller.LeftMouseButtonGesture)  # 触摸适配

        # 创建内容容器
        self.content_widget = QWidget(self)
        self.setWidget(self.content_widget)

        # 内容布局
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(40, 20, 40, 20)
        content_layout.setSpacing(32)

        # 添加设置组
        self.add_login_settings(content_layout)
        self.add_warning_settings(content_layout)
        self.add_banner_settings(content_layout)
        self.add_app_settings(content_layout)
        content_layout.addStretch()  # 可防止展开卡片时抽搐

    # 登录相关选项
    def add_login_settings(self, layout: QLayout):
        card_group = SettingCardGroup("登录")

        # 登录方式
        self.method_select = ComboBoxSettingCard(
            configItem=self.config.loginMethod,
            icon=FIF.DEVELOPER_TOOLS,
            title="登录方式",
            content="选择用于进行自动登录的方式\n可选项：UI Automation - 定位页面元素（推荐，最稳定）、OpenCV - 图像识别、Fixed - 固定位置",
            texts=["UI Automation", "OpenCV", "Fixed"],
        )
        self.method_select.comboBox.setMinimumWidth(140)
        card_group.addSettingCard(self.method_select)

        # 跳过一次
        self.warning_switch = SwitchSettingCard(
            icon=FIF.SEND,
            title="跳过一次",
            content="下次运行时跳过自动登录，适用于公开课等需临时禁用的场景",
            configItem=self.config.loginSkipOnce,
        )
        card_group.addSettingCard(self.warning_switch)

        # 终止 SeewoAgent 服务
        self.kill_agent_switch = SwitchSettingCard(
            icon=FIF.POWER_BUTTON,
            title="终止 SeewoAgent 服务",
            content="可避免某些情况下自动登录被希沃的快捷登录打断",
            configItem=self.config.loginKillAgent,
        )
        card_group.addSettingCard(self.kill_agent_switch)

        # 直接登录
        self.directly_switch = SwitchSettingCard(
            icon=FIF.PEOPLE,
            title="跳过点击进入登录界面",
            content="适用于打开希沃时不进入白板界面（iwb）的情况",
            configItem=self.config.loginDirectly,
        )
        card_group.addSettingCard(self.directly_switch)

        # 希沃白板设置卡
        self.easinote_card = EasinoteSettingCard(self.config)
        card_group.addSettingCard(self.easinote_card)

        # 超时设置卡
        self.timeout_card = TimeoutSettingCard(self.config)
        card_group.addSettingCard(self.timeout_card)

        layout.addWidget(card_group)

    # 警告弹窗相关选项
    def add_warning_settings(self, layout: QLayout):
        card_group = SettingCardGroup("警告弹窗")

        # 启用
        self.warning_switch = SwitchSettingCard(
            icon=FIF.COMPLETED,
            title="启用警告弹窗",
            content="在运行自动登录前显示警告弹窗，在超时时长内可手动取消登录",
            configItem=self.config.warningEnabled,
        )
        card_group.addSettingCard(self.warning_switch)

        # 超时时长
        self.timeout_edit = SpinSettingCard(
            icon=FIF.REMOVE_FROM,
            title="超时时长",
            content="设置要等待的超时时长",
            configItem=self.config.warningTimeout,
            min_width=160,
        )
        card_group.addSettingCard(self.timeout_edit)
        set_enable_by(self.warning_switch.switchButton, self.timeout_edit)

        layout.addWidget(card_group)

    # 警示横幅相关选项
    def add_banner_settings(self, layout: QLayout):
        card_group = SettingCardGroup("警示横幅")

        # 启用
        self.banner_switch = SwitchSettingCard(
            icon=FIF.FLAG,
            title="启用警示横幅",
            content="运行自动运行时在屏幕顶部显示一个醒目的警示横幅",
            configItem=self.config.bannerEnabled,
        )
        card_group.addSettingCard(self.banner_switch)

        # 个性化设置卡
        self.banner_style_card = BannerStyleSettingCard(self.config)
        card_group.addSettingCard(self.banner_style_card)
        set_enable_by(self.banner_switch.switchButton, self.banner_style_card)

        layout.addWidget(card_group)

    # 应用相关选项
    def add_app_settings(self, layout: QLayout):
        card_group = SettingCardGroup("应用")

        self.max_retries_edit = SpinSettingCard(
            icon=FIF.SYNC,
            title="最大重试次数",
            content="设置自动登录失败时的最大重试次数",
            configItem=self.config.appMaxRetries,
            min_width=160,
        )
        card_group.addSettingCard(self.max_retries_edit)

        self.log_level_select = ComboBoxSettingCard(
            configItem=self.config.appLogLevel,
            icon=FIF.DEVELOPER_TOOLS,
            title="日志级别",
            content="设置应用的日志记录级别",
            texts=["调试", "信息", "警告", "错误", "严重"],
        )
        card_group.addSettingCard(self.log_level_select)

        self.reset_button = PushSettingCard(
            text="重置",
            icon=FIF.CANCEL,
            title="重置配置",
            content="将所有配置项重置为默认值",
        )
        self.reset_button.clicked.connect(self.reset_config)
        card_group.addSettingCard(self.reset_button)

        layout.addWidget(card_group)

    def reset_config(self):
        """重置配置为默认值"""
        title = "确认要重置配置吗？"
        content = "所有已编辑的设置将丢失，是否继续？"
        w = MessageBox(title, content, self)

        w.setClosableOnMaskClicked(True)

        if w.exec():
            # 重置设置
            config_file = get_executable_path() / "config.json"
            logging.debug(f"清空配置文件: {config_file}")
            config_file.write_text("", encoding="utf-8")
            logging.info("配置已重置")

            # 弹出提示
            InfoBar.success(
                title="设置已重置",
                content="重启后生效",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )


class AboutPage(SmoothScrollArea):
    """设置 - 关于页"""

    def __init__(self):
        super().__init__()
        self.setObjectName("AboutPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        # 创建滚动区域
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        QScroller.grabGesture(self.viewport(), QScroller.LeftMouseButtonGesture)

        # 创建内容容器
        content_widget = QWidget(self)
        content_widget.setMaximumWidth(700)
        self.setAlignment(Qt.AlignHCenter)
        self.setWidget(content_widget)

        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(20)

        # Banner
        self.banner_area = CardWidget()
        banner_layout = QVBoxLayout(self.banner_area)
        banner_layout.setAlignment(Qt.AlignTop)
        banner_layout.setContentsMargins(24, 16, 24, 16)

        self._banner_img_orig = QPixmap(get_resource("banner.png"))
        self.banner_image = ImageLabel(self._banner_img_orig)
        self.banner_image.setBorderRadius(8, 8, 8, 8)
        self.banner_image.scaledToWidth(560)
        self.banner_image.setStyleSheet("border-radius: 8px;")

        title = TitleLabel("EasiAuto", self)
        subtitle = SubtitleLabel("版本 1.0.1", self)

        banner_layout.addWidget(self.banner_image)
        banner_layout.addWidget(title)
        banner_layout.addWidget(subtitle)

        layout.addWidget(self.banner_area)

        # Product Info
        self.product_info_area = CardWidget()
        product_info_layout = QVBoxLayout(self.product_info_area)
        product_info_layout.setAlignment(Qt.AlignTop)
        product_info_layout.setContentsMargins(24, 16, 24, 16)

        product_text = BodyLabel("一个用于自动登录希沃白板的小工具")
        product_info_layout.addWidget(product_text)

        github_link = HyperlinkLabel(QUrl("https://github.com/hxabcd/easiauto"), "GitHub 仓库")
        product_info_layout.addWidget(github_link)

        layout.addWidget(self.product_info_area)

        # Author Info
        self.info_area = CardWidget()
        author_info_layout = QVBoxLayout(self.info_area)
        author_info_layout.setAlignment(Qt.AlignTop)
        author_info_layout.setContentsMargins(24, 16, 24, 16)

        author_text = BodyLabel("作者：HxAbCd")
        author_link1 = HyperlinkLabel(QUrl("https://0xabcd.dev"), "Website")
        author_link2 = HyperlinkLabel(QUrl("https://space.bilibili.com/336325343"), "Bilibili")
        author_link3 = HyperlinkLabel(QUrl("https://github.com/hxabcd"), "Github")

        author_info_layout.addWidget(author_text)
        author_info_layout.addWidget(author_link1)
        author_info_layout.addWidget(author_link2)
        author_info_layout.addWidget(author_link3)

        layout.addWidget(self.info_area)
        layout.addStretch()


class AutomationStatusBar(QWidget):
    """自动化页 - 状态栏"""

    def __init__(self, manager: CiAutomationManager | None = None):
        super().__init__()
        self.manager = manager

        self.setFixedHeight(42)
        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(16, 4, 16, 0)

        self.status_badge = DotInfoBadge.error()
        self.status_label = BodyLabel("未初始化")

        self.action_button = PushButton(icon=FIF.POWER_BUTTON, text="终止")
        self.action_button.clicked.connect(self.handle_action_button_clicked)
        self.action_button.setEnabled(False)

        self.option_button = TransparentPushButton(icon=FIF.DEVELOPER_TOOLS, text="高级选项")

        layout.addWidget(StrongBodyLabel("ClassIsland"))
        layout.addSpacing(12)
        layout.addWidget(self.status_badge)
        layout.addWidget(self.status_label)
        layout.addSpacing(6)
        layout.addWidget(self.action_button)
        layout.addStretch(1)
        layout.addWidget(self.option_button)

    def update_status(self, status: Literal[-1, 0, 1] | None = None):
        if status is None:
            if self.manager:
                status = 1 if self.manager.is_ci_running else 0
            else:
                status = -1

        logging.debug(f"更新 ClassIsland 状态: {status}")
        match status:
            case -1:
                self.status_badge.level = InfoLevel.ERROR
                self.status_badge.update()
                self.status_label.setText("未初始化")
                self.action_button.setEnabled(False)
            case 1:
                self.status_badge.level = InfoLevel.SUCCESS
                self.status_badge.update()
                self.status_label.setText("运行中")
                self.action_button.setText("终止")
                self.action_button.setEnabled(True)
            case 0:
                self.status_badge.level = InfoLevel.INFOAMTION
                self.status_badge.update()
                self.status_label.setText("未运行")
                self.action_button.setText("启动")
                self.action_button.setEnabled(True)

    def handle_action_button_clicked(self):
        assert self.manager
        if self.manager.is_ci_running:
            logging.info("用户点击终止 ClassIsland")
            self.manager.close_ci()
        else:
            logging.info("用户点击启动 ClassIsland")
            self.manager.open_ci()


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

        self.action_run = Action(FIF.PLAY, "运行", triggered=self._on_run)
        self.action_export = Action(FIF.SHARE, "导出", triggered=self._on_export)
        self.action_remove = Action(FIF.CANCEL_MEDIUM, "删除", triggered=lambda: self.actionRemove.emit(self.list_item))

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
            logging.debug(f"自动化 {self.automation.guid} 启用状态改变: {checked}")
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
        logging.debug(f"更新自动化卡片显示: {automation.item_display_name}")
        self.automation = automation
        self.name_label.setText(automation.item_display_name)
        # 断开连接以避免触发信号
        self.switch.checkedChanged.disconnect()
        self.switch.setChecked(automation.enabled)
        self.switch.checkedChanged.connect(self.on_switch_toggled)

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.LeftButton:
            self.itemClicked.emit(self.list_item)
        super().mousePressEvent(event)


class AutomationManageSubpage(QWidget):
    """自动化页 - 自动化管理 子页面"""

    def __init__(self, manager: CiAutomationManager | None):
        super().__init__()
        self.manager = manager
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
        self.action_bar.addAction(Action(FIF.ADD, "添加", triggered=self._add_automation))
        self.action_bar.addAction(Action(FIF.SYNC, "刷新", triggered=lambda: self._init_selector(reload=True)))

        self.auto_list = ListWidget()
        self.auto_list.setSpacing(3)

        self.selector_layout.addWidget(self.action_bar)
        self.selector_layout.addWidget(self.auto_list)

        # 右侧：编辑器
        self.editor_widget = QWidget()
        self.editor_layout = QVBoxLayout(self.editor_widget)

        # 新自动化提示
        self.new_auto_hint = CardWidget()

        self.new_auto_hint.setFixedHeight(48)
        self.new_auto_hint.setContentsMargins(12, 2, 12, 2)
        hint_layout = QHBoxLayout(self.new_auto_hint)
        hint_icon = IconInfoBadge.attension(FIF.RINGER)
        hint_icon.setFixedSize(24, 24)
        hint_icon.setIconSize(QSize(12, 12))
        hint_text = QLabel("正在编辑新自动化")
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

        form_layout.addRow("账号", self.account_edit)
        form_layout.addRow("密码", self.password_edit)
        form_layout.addRow("科目", self.subject_edit)
        form_layout.addRow("教师 (可选)", self.teacher_edit)
        form_layout.addRow("提前时间 (秒)", self.pretime_edit)

        self.subject_edit.setCurrentIndex(-1)
        self.pretime_edit.setRange(0, 900)

        self.save_button = PrimaryPushButton("保存")
        self.save_button.clicked.connect(self._handle_save_automation)

        self.editor_layout.addWidget(self.form)
        self.editor_layout.addStretch(1)
        self.editor_layout.addWidget(self.save_button)
        self.editor_widget.setDisabled(True)

        layout.addWidget(self.selector_widget, 1)
        layout.addWidget(Separator("vertical"))
        layout.addWidget(self.editor_widget, 1)

        if manager:
            # 订阅 Manager 的数据变更信号
            manager.automationCreated.connect(self._on_automation_created)
            manager.automationUpdated.connect(self._on_automation_updated)
            manager.automationDeleted.connect(self._on_automation_deleted)
            self._init_selector()
            self._init_editor()

    def _init_selector(self, reload: bool = False):
        """初始化自动化列表"""
        if not self.manager:
            return

        if reload:
            self.manager.reload_config()

        self.auto_list.clear()

        for _, automation in self.manager.automations.items():
            self._add_automation_item(automation)

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
        if not self.manager:
            logging.warning("无法添加自动化: 管理器未初始化")
            return

        logging.info("添加新的自动化")
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
        if not self.manager:
            return

        if reload:
            self.manager.reload_config()

        self.subject_edit.clear()

        for subject in self.manager.list_subjects():
            self.subject_edit.addItem(subject.name, userData=subject.id)

    def _update_editor(self, auto: EasiAutomation):
        """更新编辑器数据"""
        self.current_automation = auto

        self.new_auto_hint.setVisible(self.is_new_automation)
        self.automation_name_label.setText(auto.item_display_name)

        self.account_edit.setText(auto.account)
        self.password_edit.setText(auto.password)

        self.subject_edit.setCurrentIndex(-1)
        if self.manager:
            subject = self.manager.get_subject_by_id(auto.subject_id)
            if subject:
                subject_item = self.subject_edit.findData(subject.id)
                if subject_item != -1:
                    self.subject_edit.setCurrentIndex(subject_item)

        self.teacher_edit.setText(auto.teacher_name)
        self.pretime_edit.setValue(auto.pretime)

        self.editor_widget.setEnabled(auto.enabled)

    def _clear_editor(self):
        """清空编辑器数据"""
        self.account_edit.clear()
        self.password_edit.clear()
        self.subject_edit.setCurrentIndex(-1)
        self.teacher_edit.clear()
        self.pretime_edit.setValue(0)

        self.editor_widget.setDisabled(True)

    def _save_form(self):
        """保存编辑器数据"""
        if not self.manager or not self.current_automation:
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
        if self.manager.get_subject_by_id(subject_id) is None:
            raise ValueError("无效科目")
        automation.subject_id = subject_id

        automation.teacher_name = self.teacher_edit.text()
        automation.pretime = self.pretime_edit.value()

        # 通过 Manager 保存，不直接修改 item
        if self.manager.get_automation_by_guid(automation.guid) is None:
            # 新建
            self.manager.create_automation(automation)
        else:
            # 更新
            self.manager.update_automation(automation.guid, **automation.model_dump())

    def _handle_save_automation(self):
        """保存自动化数据"""
        try:
            logging.debug("保存自动化数据")
            self._save_form()
            logging.info("自动化数据保存成功")
            # 保存成功后重置新建状态标志
            if self.is_new_automation:
                self.is_new_automation = False
        except ValueError as e:
            logging.warning(f"自动化数据保存失败: {e}")
            InfoBar.error(
                title="错误",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _on_item_clicked(self, item: QListWidgetItem):
        """列表项点击事件"""
        automation = item.data(Qt.UserRole)
        logging.debug(f"点击自动化项目: {automation.item_display_name}")
        self.current_list_item = item

        self.is_new_automation = False
        self._update_editor(automation)

    def _on_automation_enabled_changed(self, guid: str, enabled: bool):
        """处理 Card 中开关状态改变（通过 Manager 更新）"""
        logging.debug(f"自动化启用状态改变 - GUID: {guid}, 启用: {enabled}")
        if self.manager:
            self.manager.update_automation(guid, enabled=enabled)

    def _handle_action_run(self, guid: str):
        """操作 - 运行自动化"""
        if not self.manager:
            logging.warning("无法运行自动化: 管理器未初始化")
            return

        automation = self.manager.get_automation_by_guid(guid)
        if not automation:
            logging.error(f"无法找到自动化: {guid}")
            return

        logging.info(f"开始运行自动化: {automation.item_display_name}")

        # 最小化设置界面
        app = QApplication.instance() or QApplication([])
        main_window = app.activeWindow()
        if main_window:
            main_window.showMinimized()

        from automator import CVAutomator, FixedAutomator, UIAAutomator
        from components import WarningBanner
        from main import config

        # 显示警示横幅
        if config.Banner.Enabled:
            try:
                screen = app.primaryScreen().geometry()
                self.banner = WarningBanner(config.Banner)
                self.banner.setGeometry(0, 80, screen.width(), 140)  # 顶部横幅
                self.banner.show()
            except Exception:
                logging.exception("显示横幅时出错，跳过横幅")

        # 执行登录
        logging.debug(f"当前设置的登录方案: {config.Login.Method}")
        match config.Login.Method:  # 选择登录方案
            case "UIAutomation":
                automatorType = UIAAutomator
            case "OpenCV":
                automatorType = CVAutomator
            case "FixedPosition":
                automatorType = FixedAutomator
            case _:
                logging.warning("未知方案，已回滚至默认值 (UI Automation)")
                automatorType = UIAAutomator

        automator = automatorType(automation.account, automation.password, config, config.App.MaxRetries)

        automator.start()
        automator.finished.connect(self._clean_up_after_run)

    def _clean_up_after_run(self):
        """清理运行后的资源"""
        if hasattr(self, "banner"):
            self.banner.close()
            del self.banner

    def _handle_action_export(self, guid: str):
        """操作 - 导出自动化"""
        if not self.manager:
            logging.warning("无法导出自动化: 管理器未初始化")
            return

        automation = self.manager.get_automation_by_guid(guid)
        if not automation:
            logging.error(f"无法找到自动化: {guid}")
            return

        logging.info(f"导出自动化脚本: {automation.item_display_name}")
        try:
            content = f"""@echo off
chcp 65001 >nul
cd /d "{get_executable_path()}"
{get_executable()} login -a "{automation.account}" -p "{automation.password}"
"""
            name = automation.item_display_name + ".bat"
            logging.debug(f"创建脚本文件: {name}")
            create_script(bat_content=content, file_name=name)
            logging.info(f"导出脚本成功: {name}")

            InfoBar.success(
                title="创建成功",
                content=f"已在桌面创建 {name}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        except Exception as e:
            logging.exception(f"创建脚本失败: {e}")
            InfoBar.error(
                title="创建失败",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _handle_action_remove(self, item: QListWidgetItem):
        """操作 - 删除自动化"""
        if not self.manager:
            logging.warning("无法删除自动化: 管理器未初始化")
            return

        automation = item.data(Qt.UserRole)
        logging.info(f"删除自动化: {automation.item_display_name}")
        self.manager.delete_automation(automation.guid)

    def _on_automation_created(self, guid: str):
        """Manager 信号：自动化被创建"""
        logging.debug(f"收到自动化创建信号: {guid}")
        if not self.manager:
            logging.warning("管理器未初始化")
            return

        automation = self.manager.get_automation_by_guid(guid)
        if not automation:
            logging.error(f"无法获取新创建的自动化: {guid}")
            return

        logging.info(f"自动化已创建: {automation.item_display_name}")
        # 添加到列表
        item = self._add_automation_item(automation)
        # 如果是新建的自动化，自动选中
        if self.is_new_automation:
            self.auto_list.setCurrentItem(item)
            self.current_list_item = item

    def _on_automation_updated(self, guid: str):
        """Manager 信号：自动化被更新"""
        logging.debug(f"收到自动化更新信号: {guid}")
        if not self.manager:
            logging.warning("管理器未初始化")
            return

        automation = self.manager.get_automation_by_guid(guid)
        if not automation:
            logging.error(f"无法获取已更新的自动化: {guid}")
            return

        logging.debug(f"自动化已更新: {automation.item_display_name}")
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
        logging.debug(f"收到自动化删除信号: {guid}")
        # 从列表中移除
        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            if item.data(Qt.UserRole).guid == guid:
                automation_name = item.data(Qt.UserRole).item_display_name
                self.auto_list.takeItem(i)
                logging.info(f"自动化已删除: {automation_name}")
                # 如果删除的是当前项，清空编辑器
                if self.current_list_item == item:
                    self.current_list_item = None
                    self._clear_editor()
                break

    def set_manager(self, manager: CiAutomationManager):
        """重设自动化管理器"""
        # 退订信号
        if self.manager:
            self.manager.automationCreated.disconnect(self._on_automation_created)
            self.manager.automationUpdated.disconnect(self._on_automation_updated)
            self.manager.automationDeleted.disconnect(self._on_automation_deleted)

        self.manager = manager
        # 订阅信号
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

        hint_icon = QLabel(pixmap=Icon(FIF.REMOVE_FROM).pixmap(96, 96))
        hint_label = TitleLabel("未能获取到 ClassIsland 路径")
        hint_desc = BodyLabel("<span style='font-size: 15px;'>EasiAuto 的「自动化」功能依赖于 ClassIsland</span>")
        hint_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions = QWidget()

        actions_layout = QHBoxLayout(actions)
        actions_layout.setSpacing(10)

        get_ci_button = PrimaryPushButton(icon=FIF.DOWNLOAD, text="获取 ClassIsland")
        get_ci_button.setFixedWidth(150)
        get_ci_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://classisland.tech")))

        browse_button = PushButton(icon=FIF.FOLDER_ADD, text="选择已有路径")
        browse_button.setFixedWidth(150)
        browse_button.clicked.connect(self.browse_ci_path)

        actions_layout.addWidget(get_ci_button)
        actions_layout.addWidget(BodyLabel("或"))
        actions_layout.addWidget(browse_button)

        layout.addWidget(hint_icon)
        layout.addSpacing(12)
        layout.addWidget(hint_label)
        layout.addWidget(hint_desc)
        layout.addSpacing(18)
        layout.addWidget(actions)

    def browse_ci_path(self):
        logging.debug("打开文件选择对话框")
        exe_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 ClassIsland 程序路径",
            "",
            "ClassIsland 可执行文件 (*.exe)",
        )

        if not exe_path:  # 取消选择
            logging.debug("用户取消了文件选择")
            return

        logging.info(f"用户选择了 ClassIsland 路径: {exe_path}")
        self.pathChanged.emit(exe_path)


class CiRunningWarnSubpage(QWidget):
    """自动化页 - CI运行警告 子页面"""

    ciClosed = Signal()

    label_text_1 = "ClassIsland 正在运行"
    label_desc_1 = "<span style='font-size: 15px;'>需要关闭 ClassIsland 才能编辑自动化</span>"
    label_text_1e = "唔，看起来 ClassIsland 还在运行呢"
    label_desc_1e = "<span style='font-size: 15px;'>这种坏事要偷偷地干啦，让 ClassIsland 大姐姐看到就不好了哦~</span>"

    label_text_2 = "无法终止 ClassIsland"
    label_desc_2 = "<span style='font-size: 15px;'>自动关闭失败，请尝试手动关闭 ClassIsland</span>"
    label_text_2e = "诶诶，情况好像不太对？！"
    lalbel_desc_2e = "<span style='font-size: 15px;'>没想到 ClassIsland 大姐姐竟然这么强势QAQ</span>"

    def __init__(self, manager: CiAutomationManager | None = None, easter_egg: bool = False):
        super().__init__()
        self.manager = manager
        self.easter_egg_enabled = easter_egg

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hint_icon = QLabel()
        self.hint_label = TitleLabel()
        self.hint_desc = BodyLabel()
        self.hint_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action_button = PrimaryPushButton(icon=FIF.POWER_BUTTON, text="终止 ClassIsland")
        self.action_button.clicked.connect(self.terminate_ci)

        layout.addWidget(self.hint_icon)
        layout.addSpacing(12)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.hint_desc)
        layout.addSpacing(18)
        layout.addWidget(self.action_button)

        self.set_text()

    def set_text(self, failed: bool = False):
        if not failed:
            self.hint_icon.setPixmap(Icon(FIF.BROOM).pixmap(96, 96))
            if self.easter_egg_enabled:
                self.hint_label.setText(self.label_text_1e)
                self.hint_desc.setText(self.label_desc_1e)
            else:
                self.hint_label.setText(self.label_text_1)
                self.hint_desc.setText(self.label_desc_1)
                self.action_button.show()
        else:
            self.hint_icon.setPixmap(Icon(FIF.QUESTION).pixmap(96, 96))
            if self.easter_egg_enabled:
                self.hint_label.setText(self.label_text_2e)
                self.hint_desc.setText(self.label_text_2e)
            else:
                self.hint_label.setText(self.label_text_2)
                self.hint_desc.setText(self.label_desc_2)
            self.action_button.hide()

    def terminate_ci(self):
        if self.manager:
            logging.info("用户点击终止 ClassIsland")
            self.manager.close_ci()


class AutomationPage(QWidget):
    """设置 - 自动化页"""

    def __init__(self):
        super().__init__()
        logging.debug("初始化自动化页面")
        self.setObjectName("AutomationPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        # 初始化CI自动化管理器
        self.manager = None
        if exe_path := get_ci_executable_path():
            logging.info("自动化管理器初始化成功")
            logging.debug(f"ClassIsland 程序位置: {exe_path}")
            self.manager = CiAutomationManager(exe_path)
        else:
            logging.warning("无法找到 ClassIsland 程序，自动化管理器初始化失败")

        self.init_ui()
        self.start_watchdog()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.status_bar = AutomationStatusBar(self.manager)

        # 主页面，下分管理页和路径选择页
        self.main_widget = QStackedWidget()

        self.path_select_page = PathSelectSubpage()
        self.ci_running_warn_page = CiRunningWarnSubpage(self.manager)
        self.manager_page = AutomationManageSubpage(self.manager)

        self.main_widget.addWidget(self.path_select_page)
        self.main_widget.addWidget(self.ci_running_warn_page)
        self.main_widget.addWidget(self.manager_page)

        self.path_select_page.pathChanged.connect(self.handle_path_changed)

        layout.addWidget(self.status_bar)
        layout.addWidget(Separator("horizontal"))
        layout.addWidget(self.main_widget)

    def start_watchdog(self):
        """启动CI运行状态监听"""
        if not self.manager:
            logging.debug("管理器未初始化，跳过状态监听")
            return

        if hasattr(self.manager, "watchdog"):
            logging.debug("状态监听已启动")
            return

        logging.info("启动 ClassIsland 状态监听")
        self.check_status()

        self.watchdog = QTimer(self)
        self.watchdog.timeout.connect(self.check_status)
        self.watchdog.start(1000)

    def check_status(self):
        """检查状态并切换页面"""
        target_page: QWidget
        if self.manager is None:
            target_page = self.path_select_page
        elif self.manager.is_ci_running:
            target_page = self.ci_running_warn_page
        else:
            target_page = self.manager_page

        if self.main_widget.currentWidget() != target_page:
            logging.debug(f"切换自动化页面到: {target_page.__class__.__name__}")
            self.main_widget.setCurrentWidget(target_page)
            if target_page == self.manager_page:
                self.manager_page._init_selector(reload=True)
            self.status_bar.update_status()

    def handle_path_changed(self, path: Path):
        """重设自动化管理器"""
        logging.info(f"尝试使用新路径初始化管理器: {path}")
        try:
            self.manager = CiAutomationManager(path)
            logging.info("自动化管理器重新初始化成功")
        except Exception as e:
            logging.error(f"自动化管理器初始化失败: {e}")
            InfoBar.error(
                title="错误",
                content="指定的目录不正确",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        self.status_bar.manager = self.manager
        self.ci_running_warn_page.manager = self.manager
        self.manager_page.set_manager(self.manager)

        self.start_watchdog()


class MainSettingsWindow(FluentWindow):
    def __init__(self):
        super().__init__()

        self.config_page = ConfigPage()
        self.automation_page = AutomationPage()
        # self.overlay_page = SettingsUI("3")
        self.about_page = AboutPage()

        self.initNavigation()
        self.initWindow()

    def initNavigation(self):
        self.addSubInterface(self.config_page, FIF.SETTING, "配置")
        self.addSubInterface(self.automation_page, FIF.AIRPLANE, "自动化")
        # self.addSubInterface(self.overlay_page, FIF.ZOOM, "浮窗")
        self.addSubInterface(self.about_page, FIF.INFO, "关于", NavigationItemPosition.BOTTOM)
        # self.navigationInterface.addSeparator()

        self.navigationInterface.setExpandWidth(180)

    def initWindow(self):
        logging.debug("初始化主设置窗口")
        self.resize(960, 640)
        self.setWindowIcon(QIcon(get_resource("easiauto.ico")))
        self.setWindowTitle("EasiAuto")
        logging.info("主设置窗口初始化完成")


def set_enable_by(switch: SwitchButton, widget: QWidget, reverse: bool = False):
    """通过开关启用组件"""
    if not reverse:
        widget.setEnabled(switch.checked)  # type: ignore

        def handle_check_change(checked: bool):
            widget.setEnabled(checked)
            if not checked and isinstance(widget, ExpandSettingCard):
                widget.setExpand(False)

        switch.checkedChanged.connect(handle_check_change)
    else:
        widget.setDisabled(switch.checked)  # type: ignore

        def handle_check_change(checked: bool):
            widget.setDisabled(checked)
            if checked and isinstance(widget, ExpandSettingCard):
                widget.setExpand(False)

        switch.checkedChanged.connect(handle_check_change)


if __name__ == "__main__":
    from utils import set_logger

    set_logger(level=logging.DEBUG)
    app = QApplication(sys.argv)

    translator = FluentTranslator()
    app.installTranslator(translator)
    setTheme(Theme.AUTO)

    window = MainSettingsWindow()
    window.show()
    sys.exit(app.exec())
