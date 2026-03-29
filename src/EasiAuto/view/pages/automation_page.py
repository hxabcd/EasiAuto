import contextlib
from enum import Enum
from pathlib import Path
from typing import assert_never

from loguru import logger

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    DotInfoBadge,
    FluentIcon,
    HorizontalSeparator,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    InfoLevel,
    LineEdit,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
    TitleLabel,
    TransparentPushButton,
)

from EasiAuto.common.config import config
from EasiAuto.common.utils import get_ci_executable
from EasiAuto.integrations.classisland_manager import classisland_manager as ci_manager
from EasiAuto.view.components import SettingCard
from EasiAuto.view.utils import Icons, get_main_container, set_enable_by

from .binding_page import BindingPage


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


class StatusBar(QWidget):
    reloadClicked = Signal()

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

        self.reload_button = TransparentPushButton(icon=FluentIcon.SYNC, text="刷新")
        self.reload_button.clicked.connect(self.reloadClicked)

        self.option_button = TransparentPushButton(icon=FluentIcon.DEVELOPER_TOOLS, text="高级选项")
        self.option_button.clicked.connect(self._show_advanced_settings)

        layout.addWidget(SubtitleLabel("ClassIsland 自动化编辑"))
        layout.addSpacing(12)
        layout.addWidget(self.status_badge)
        layout.addWidget(self.status_label)
        layout.addSpacing(6)
        layout.addWidget(self.action_button)
        layout.addStretch(1)
        layout.addWidget(self.reload_button)
        layout.addWidget(self.option_button)

        self.update_status()

    def _show_advanced_settings(self):
        """显示高级设置对话框"""
        w = AdvancedOptionsDialog(self.window())
        w.exec()

    def update_status(self, status: CIStatus | None = None):
        if status is None:
            if ci_manager:
                status = CIStatus.RUNNING if ci_manager.is_running else CIStatus.DIED
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
        if not ci_manager:
            return
        if ci_manager.is_running:
            logger.info("终止 ClassIsland")
            ci_manager.stop_ci()
        else:
            logger.info("启动 ClassIsland")
            ci_manager.start_ci()


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
            "ClassIsland 可执行文件 (ClassIsland.exe)",
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
    """自动化页 - ClassIsland 运行警告浮层"""

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
        self.action_button.setMinimumWidth(240)

        layout.addLayout(self.icon_container)
        layout.addSpacing(12)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.hint_desc)
        layout.addSpacing(18)
        layout.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.set_text()
        with contextlib.suppress(KeyError):
            SettingCard.index["Debug.EasterEggEnabled"].valueChanged.connect(lambda _: self.set_text())

    def set_text(self, failed: bool = False):
        if not failed:
            self.hint_icon.setIcon(Icons.ClassIsland)
            if config.Debug.EasterEggEnabled:
                self.hint_label.setText(self.labelE_running_text)
                self.hint_desc.setText(self.labelE_running_desc)
            else:
                self.hint_label.setText(self.label_running_text)
                self.hint_desc.setText(self.label_running_desc)
                self.action_button.show()
        else:
            self.hint_icon.setIcon(FluentIcon.QUESTION)
            if config.Debug.EasterEggEnabled:
                self.hint_label.setText(self.labelE_failed_text)
                self.hint_desc.setText(self.labelE_failed_text)
            else:
                self.hint_label.setText(self.label_failed_text)
                self.hint_desc.setText(self.label_failed_desc)
            self.action_button.hide()

    def terminate_ci(self):
        if ci_manager:
            logger.info("用户点击终止 ClassIsland")
            ci_manager.stop_ci()

    def mousePressEvent(self, event):
        event.accept()


class AutomationPage(QWidget):
    bindingsChanged = Signal()
    editClicked = Signal(str)  # automation_id

    def __init__(self):
        super().__init__()
        logger.debug("初始化自动化页")
        self.setObjectName("AutomationPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        # 初始化 ClassIsland 管理器
        # TODO: 使用新版统一接口
        try:
            if config.ClassIsland.AutoPath:
                exe_path = get_ci_executable()
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
                ci_manager.initialize(exe_path)  # type: ignore (manager: _CiManagerProxy)
                logger.success("ClassIsland 管理器初始化成功")
            except Exception as e:
                logger.warning(f"ClassIsland 管理器初始化失败: {e}")
        else:
            logger.warning(f"{'未找到 ClassIsland 路径' if not exe_path else '路径无效'}, 跳过初始化")

        self.init_ui()
        self.start_watcher()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.status_bar = StatusBar()
        self.main_widget = QStackedWidget()

        self.path_select_page = PathSelectSubpage()
        self.overlay_page = CiRunningWarnOverlay()
        self.binding_page = BindingPage()

        self.binding_page.bindingsChanged.connect(self.bindingsChanged)
        self.binding_page.editClicked.connect(self.editClicked)
        self.status_bar.reloadClicked.connect(lambda: self.binding_page.reload(reload=True))

        self.main_widget.addWidget(self.path_select_page)
        self.main_widget.addWidget(self.overlay_page)
        self.main_widget.addWidget(self.binding_page)

        if ci_manager:
            self.main_widget.setCurrentWidget(self.binding_page)

        self.path_select_page.pathChanged.connect(self.handle_path_changed)

        layout.addWidget(self.status_bar)
        layout.addWidget(HorizontalSeparator())
        layout.addWidget(self.main_widget)

    def start_watcher(self):  # TODO: 使用新版统一接口
        """启动 ClassIsland 运行状态监听"""
        if not ci_manager:
            logger.debug("管理器未初始化, 跳过状态监听")
            return

        if hasattr(self, "watcher"):
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
        if ci_manager is None:
            target_page = self.path_select_page
        elif ci_manager.is_running:
            target_page = self.overlay_page
        else:
            target_page = self.binding_page

        if self.main_widget.currentWidget() != target_page:
            logger.debug(f"切换自动化页面到: {target_page.__class__.__name__}")
            self.main_widget.setCurrentWidget(target_page)
            if target_page == self.binding_page:
                self.binding_page.reload()
            self.status_bar.update_status()

    def handle_path_changed(self, path: Path):
        """重设 ClassIsland 管理器"""

        logger.info(f"尝试使用 {path} 初始化管理器")
        try:
            ci_manager.initialize(path)  # type: ignore (manager: _CiManagerProxy)
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


        self.start_watcher()
