from loguru import logger

from PySide6.QtCore import QSize, QTimer, Signal
from PySide6.QtGui import QIcon
from qfluentwidgets import (
    FluentIcon,
    MSFluentWindow,
    NavigationItemPosition,
    SplashScreen,
    SystemThemeListener,
    isDarkTheme,
    qconfig,
    setTheme,
)

from EasiAuto.common.utils import get_resource
from EasiAuto.view.pages import AboutPage, AutomationPage, ConfigPage, ProfilePage, UpdatePage


class MainWindow(MSFluentWindow):
    runAutomation = Signal(str, str)

    def __init__(self):
        logger.debug("初始化界面")
        super().__init__()
        self._init_window()

        # 启动页面
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(102, 102))
        logger.debug("显示启动页面")
        self.show()

        self.config_page = ConfigPage()
        self.automation_page = AutomationPage()
        self.profile_page = ProfilePage()
        self.update_page = UpdatePage()
        self.about_page = AboutPage()

        self._init_navigation()
        self._init_signals()

        self.themeListener.start()

        logger.success("界面初始化完成")
        self.splashScreen.finish()

    def _init_navigation(self):
        self.addSubInterface(self.config_page, FluentIcon.SETTING, "配置")
        self.addSubInterface(self.profile_page, FluentIcon.DOCUMENT, "档案")
        self.addSubInterface(self.automation_page, FluentIcon.AIRPLANE, "自动化")
        self.addSubInterface(self.update_page, FluentIcon.UPDATE, "更新")
        self.addSubInterface(self.about_page, FluentIcon.INFO, "关于", position=NavigationItemPosition.BOTTOM)

    def _init_window(self):
        self.setObjectName("MainWindow")
        self.setWindowIcon(QIcon(get_resource("EasiAuto.ico")))
        self.setWindowTitle("EasiAuto")
        self.setMinimumSize(800, 500)
        self.resize(960, 640)

        self.themeListener = SystemThemeListener(self)
        self.themeListener.setObjectName("SystemThemeListener")
        qconfig.themeChanged.connect(setTheme)

    def _init_signals(self):
        # 登录请求
        self.profile_page.runAutomation.connect(self.runAutomation)

        # 数据同步
        self.profile_page.profileChanged.connect(self._on_profile_changed)
        self.automation_page.editClicked.connect(self._on_edit_automation)

    def _on_profile_changed(self):
        self.automation_page.binding_page.reload()

    def _on_edit_automation(self, automation_id: str):
        self.profile_page.manager_page.scroll_to_automation(automation_id)
        self.switchTo(self.profile_page)

    def closeEvent(self, e):
        self.themeListener.terminate()  # 停止监听器线程
        super().closeEvent(e)

    def _onThemeChangedFinished(self):
        super()._onThemeChangedFinished()

        # 云母特效启用时需要增加重试机制
        if self.isMicaEffectEnabled():
            QTimer.singleShot(100, lambda: self.windowEffect.setMicaEffect(self.winId(), isDarkTheme()))
