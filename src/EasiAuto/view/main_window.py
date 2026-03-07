from loguru import logger

from PySide6.QtCore import QSize, QTimer
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
from EasiAuto.view.pages import AboutPage, AutomationPage, ConfigPage, UpdatePage


class MainWindow(MSFluentWindow):
    def __init__(self):
        logger.debug("初始化界面")
        super().__init__()
        self.initWindow()

        # 启动页面
        self.splashScreen = SplashScreen(self.windowIcon(), self)  # TODO: 无法显示，貌似出现于重构结构后
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

    def initNavigation(self):
        self.addSubInterface(self.config_page, FluentIcon.SETTING, "配置")
        self.addSubInterface(self.automation_page, FluentIcon.AIRPLANE, "自动化")
        self.addSubInterface(self.update_page, FluentIcon.UPDATE, "更新")
        self.addSubInterface(self.about_page, FluentIcon.INFO, "关于", position=NavigationItemPosition.BOTTOM)

    def initWindow(self):
        self.setObjectName("MainWindow")
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
