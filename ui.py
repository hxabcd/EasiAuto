import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QLayout,
    QScroller,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ComboBoxSettingCard,
    ExpandGroupSettingCard,
    ExpandSettingCard,
    FluentTranslator,
    FluentWindow,
    HyperlinkLabel,
    ImageLabel,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    NavigationItemPosition,
    PushSettingCard,
    SettingCardGroup,
    SmoothScrollArea,
    SubtitleLabel,
    SwitchButton,
    Theme,
    TitleLabel,
    qconfig,
    setTheme,
)
from qfluentwidgets import FluentIcon as FIF

from components import ColorSettingCard, EditSettingCard, RangeSettingCard, SpinSettingCard, SwitchSettingCard
from config import QfwEasiautoConfig
from utils import get_executable_dir


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

        config_file = get_executable_dir() / "config.json"
        self.config = QfwEasiautoConfig()
        qconfig.load(config_file, self.config)

        self.init_ui()

    def init_ui(self):
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
            config_file = get_executable_dir() / "config.json"
            config_file.write_text("", encoding="utf-8")

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

        self._banner_img_orig = QPixmap("resources/banner.png")
        self.banner_image = ImageLabel(self._banner_img_orig)
        self.banner_image.setBorderRadius(8, 8, 8, 8)
        self.banner_image.scaledToWidth(560)
        self.banner_image.setStyleSheet("border-radius: 8px;")

        title = TitleLabel("EasiAuto", self)
        subtitle = SubtitleLabel("版本 1.0.0", self)

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


class MainSettingsWindow(FluentWindow):
    def __init__(self):
        super().__init__()

        self.config_page = ConfigPage()
        # self.automation_page = SettingsUI("2")
        # self.overlay_page = SettingsUI("3")
        self.about_page = AboutPage()

        self.initNavigation()
        self.initWindow()

    def initNavigation(self):
        self.addSubInterface(self.config_page, FIF.SETTING, "配置")
        # self.addSubInterface(self.automation_page, FIF.AIRPLANE, "自动化")
        # self.addSubInterface(self.overlay_page, FIF.ZOOM, "浮窗")
        self.addSubInterface(self.about_page, FIF.INFO, "关于", NavigationItemPosition.BOTTOM)
        # self.navigationInterface.addSeparator()

        self.navigationInterface.setExpandWidth(180)

    def initWindow(self):
        self.resize(960, 640)
        self.setWindowIcon(QIcon("resources/easiauto.ico"))
        self.setWindowTitle("EasiAuto")


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
    app = QApplication(sys.argv)

    translator = FluentTranslator()
    app.installTranslator(translator)
    setTheme(Theme.AUTO)

    window = MainSettingsWindow()
    window.show()
    sys.exit(app.exec())
