import time

from loguru import logger

from PySide6.QtCore import QSize, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
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

from EasiAuto.core.utils import get_resource
from EasiAuto.models.profile import BaseAutomation
from EasiAuto.view.components import PopupStackedWidget
from EasiAuto.view.pages import AboutPage, AutomationPage, ConfigPage, ProfilePage, UpdatePage


class MainWindow(MSFluentWindow):
    runAutomation = Signal(BaseAutomation)

    def __init__(self):
        logger.debug("初始化界面")
        super().__init__()
        self._upgrade_page_animation()
        self._init_window()

        # 启动页面
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(102, 102))
        logger.debug("显示启动页面")
        self.show()

        # 事件循环尚未启动：手动泵出首帧，让启动画面在构建期间保持可见
        deadline = time.monotonic() + 0.1
        while time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.005)

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

    def _upgrade_page_animation(self):
        """将导航页切换动画替换为高刷新率实现

        MSFluentWindow 内建 StackedWidget 的动画由 QAbstractAnimation 驱动
        （实测约 53Hz），此处替换其内部 view 为 PopupStackedWidget。
        """
        wrapper = self.stackedWidget
        old_view = wrapper.view
        new_view = PopupStackedWidget(wrapper)
        # 新 view 需进入外壳布局（replaceWidget），否则无布局管理，页面会缩成小矩形
        wrapper.hBoxLayout.replaceWidget(old_view, new_view)
        wrapper.view = new_view  # type: ignore[reportAttributeAccessIssue]  # 刻意替换为兼容实现
        new_view.currentChanged.connect(wrapper.currentChanged)
        old_view.deleteLater()

    def _init_window(self):
        self.setObjectName("MainWindow")
        self.setWindowIcon(QIcon(get_resource("icons/EasiAuto.ico")))
        self.setWindowTitle("EasiAuto")
        self.setMinimumSize(800, 500)
        self.resize(960, 640)

        self.themeListener = SystemThemeListener(self)
        self.themeListener.setObjectName("SystemThemeListener")
        qconfig.themeChanged.connect(setTheme)

    def _init_signals(self):
        # 登录请求
        self.profile_page.runAutomation.connect(self.runAutomation.emit)

        # 数据同步
        self.automation_page.editClicked.connect(self._on_edit_automation)

    def _on_edit_automation(self, automation_id: str):
        self.profile_page.manager_page.scroll_to_automation(automation_id)
        self.switchTo(self.profile_page)

    def switch_to_interface(self, object_name: str) -> bool:
        """按 objectName 切换到导航页面，找不到返回 False"""
        for i in range(self.stackedWidget.count()):
            page = self.stackedWidget.widget(i)
            if page is not None and page.objectName() == object_name:
                self.switchTo(page)
                return True
        return False

    def closeEvent(self, e):
        self.themeListener.terminate()  # 停止监听器线程
        super().closeEvent(e)

    def _onThemeChangedFinished(self):
        super()._onThemeChangedFinished()

        # 云母特效启用时需要增加重试机制
        if self.isMicaEffectEnabled():
            QTimer.singleShot(100, lambda: self.windowEffect.setMicaEffect(self.winId(), isDarkTheme()))
