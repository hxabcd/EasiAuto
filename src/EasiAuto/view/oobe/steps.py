from __future__ import annotations

from pathlib import Path
from typing import cast

from loguru import logger

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    IconWidget,
    ImageLabel,
    InfoBar,
    InfoBarPosition,
    PushSettingCard,
    StrongBodyLabel,
    Theme,
    TitleLabel,
    setTheme,
)

from EasiAuto import __version__
from EasiAuto.automation.utils import resolve_easinote_path
from EasiAuto.core.utils import (
    create_shortcut,
    get_ci_executable,
    get_resource,
    get_start_menu_programs,
)
from EasiAuto.models.config import LoginMethod, config
from EasiAuto.view.components import SettingCard, SettingCardType
from EasiAuto.view.components.setting_card import ExpandSelectorSettingCard
from EasiAuto.view.oobe.oobe_window import OobeStep, OobeWindow


class WelcomeStep(OobeStep):
    title = "欢迎"

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 32, 24, 4)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = ImageLabel(get_resource("icons/EasiAuto.ico"))
        icon.setScaledContents(True)
        icon.setFixedSize(96, 96)

        title = TitleLabel("EasiAuto")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        # desc = BodyLabel()
        # desc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        version = CaptionLabel(f"v{__version__}")
        version.setTextColor(QColor("#878787"), QColor("#b5b5b5"))
        version.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)
        # layout.addWidget(desc)
        layout.addWidget(version)
        layout.addStretch(1)


class BasicStep(OobeStep):
    title = "基本"

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        intro = BodyLabel("配置 EasiAuto 的基本设置。")
        intro.setWordWrap(True)

        self.telemetry_card = SettingCard.from_config_item(config.get_item("App.TelemetryEnabled"), parent=self)

        layout.addWidget(intro)
        layout.addWidget(self.telemetry_card)
        layout.addStretch(1)


class ThemeStep(OobeStep):
    title = "外观"

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        desc = BodyLabel("设置 EasiAuto 的外观主题。")
        desc.setWordWrap(True)

        self.theme_card = SettingCard.from_config_item(config.get_item("App.Theme"), parent=self)
        self.theme_card = cast(ExpandSelectorSettingCard, self.theme_card)
        self.theme_card.setAlwaysExpand(True)
        self.theme_card.valueChanged.connect(lambda t: setTheme(Theme(t.value)))

        layout.addWidget(desc)
        layout.addWidget(self.theme_card)
        layout.addStretch(1)


class LoginMethodStep(OobeStep):
    title = "登录方式"

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        desc = BodyLabel("选择自动登录的方式。")
        desc.setWordWrap(True)

        self.card = SettingCard.from_config_item(config.get_item("Login.Method"), parent=self)
        self.card = cast(ExpandSelectorSettingCard, self.card)
        self.card.setAlwaysExpand(True)

        layout.addWidget(desc)
        layout.addWidget(self.card)
        layout.addStretch(1)


class PatchStep(OobeStep):
    title = "希沃白板"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        from EasiAuto.view.components.patch import PatcherSettingCard

        desc = BodyLabel("修补希沃白板登录组件。")
        desc.setWordWrap(True)

        self.card = PatcherSettingCard(parent=self)
        # 修补期间禁用导航按钮并提示，完成后恢复
        self.card.started.connect(self._on_patch_started)
        self.card.finished.connect(self._on_patch_finished)

        # 说明文本
        note1 = BodyLabel(
            "修补会将登录相关的DLL组件写入希沃白板安装目录，从而支持已登录检查与令牌投递登录。\n"
            "修补需要管理员权限，过程中将弹出 UAC 确认窗口。\n"
            "随时可在主界面“配置”页中开启或撤销修补。"
        )
        note1.setWordWrap(True)
        note1.setTextColor(QColor("#878787"), QColor("#b5b5b5"))

        self.note2 = BodyLabel("已选择令牌投递登录，必须修补才能正常使用。")
        self.note2.setWordWrap(True)
        self.note2.hide()

        layout.addWidget(desc)
        layout.addWidget(self.card)
        layout.addWidget(note1)
        layout.addWidget(self.note2)
        layout.addStretch(1)

    def update_patched_ui(self):
        if config.Login.Method == LoginMethod.TOKEN:
            self.note2.show()
            from EasiAuto.automation.easinote_patcher import is_easinote_patched

            if self._path is not None:
                self.set_next_enabled(is_easinote_patched(self._path))
        else:
            self.note2.hide()
            self.set_next_enabled(True)

    def on_enter(self) -> None:
        self._path, _ = resolve_easinote_path()
        self.update_patched_ui()

    def on_leave(self) -> None:
        self.set_next_enabled(True)

    def _on_patch_started(self):
        self.set_busy(True, "修补中")

    def _on_patch_finished(self, ok: bool) -> None:
        self.set_busy(False)
        self.update_patched_ui()


class SystemStep(OobeStep):
    title = "系统"

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)

        desc = BodyLabel("设置 EasiAuto 的系统集成功能。")
        desc.setWordWrap(True)

        self.desktop_card = SettingCard(
            card_type=SettingCardType.SWITCH,
            icon=FluentIcon.FOLDER,
            title="创建桌面快捷方式",
            parent=self,
        )
        self.desktop_card.switchButton.setChecked(True)

        self.start_menu_card = SettingCard(
            card_type=SettingCardType.SWITCH,
            icon=FluentIcon.APPLICATION,
            title="创建开始菜单快捷方式",
            parent=self,
        )
        self.start_menu_card.switchButton.setChecked(True)

        layout.addWidget(desc)
        layout.addSpacing(6)
        layout.addWidget(self.desktop_card)
        layout.addWidget(self.start_menu_card)
        layout.addStretch(1)

    def create_shortcuts(self) -> None:
        """按勾选状态创建快捷方式（OOBE 完成时调用）"""
        if self.desktop_card.switchButton.isChecked():
            create_shortcut(args="", name="EasiAuto")

        if self.start_menu_card.switchButton.isChecked():
            programs_dir = get_start_menu_programs()
            if programs_dir:
                create_shortcut(args="", name="EasiAuto", folder=programs_dir)


class ClassIslandStep(OobeStep):
    title = "ClassIsland 集成"
    skippable = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self._detected_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        desc = BodyLabel("设置 EasiAuto 的 ClassIsland「自动化」集成功能。")
        desc.setWordWrap(True)

        locate_card = PushSettingCard(
            text="浏览…",
            icon=FluentIcon.SEARCH,
            title="ClassIsland 所在路径",
            content="",
            parent=self,
        )
        self.status_icon = locate_card.iconLabel
        self.status_title = locate_card.titleLabel
        self.status_path = locate_card.contentLabel
        self.status_icon.setFixedSize(20, 20)
        locate_card.setFixedHeight(70)
        locate_card.button.setIcon(FluentIcon.FOLDER_ADD.icon())
        locate_card.clicked.connect(self._browse)

        # 说明文本
        note = BodyLabel(
            "检测到 ClassIsland 后，EasiAuto 可配合其在课前自动执行登录任务。\n"
            "具体的科目绑定可在完成向导后，前往主界面“自动化”页配置。"
        )
        note.setWordWrap(True)
        note.setTextColor(QColor("#878787"), QColor("#b5b5b5"))

        layout.addWidget(desc)
        layout.addWidget(locate_card)
        layout.addWidget(note)
        layout.addStretch(1)

    def on_enter(self) -> None:
        self.set_next_enabled(self._detected_path is not None)
        self._detect()

    def on_leave(self) -> None:
        self.set_next_enabled(True)

    def _detect(self) -> None:
        """自动检测 ClassIsland 路径，检测到时写入自动路径模式"""
        if config.ClassIsland.AutoPath:
            if (path := get_ci_executable()) and path.exists():
                self._detected_path = path
                self.status_icon.setIcon(FluentIcon.COMPLETED)
                self._apply_status(f"自动获取: {path}")
                self.set_next_enabled(True)
            else:
                self._detected_path = None
                self.status_icon.setIcon(FluentIcon.SEARCH)
                self._apply_status("未能自动获取到路径，请手动选择 ClassIsland 可执行文件")
        elif (path := Path(config.ClassIsland.Path)) and path.exists():
            self._detected_path = path
            self.status_icon.setIcon(FluentIcon.COMPLETED)
            self._apply_status(f"手动选择: {path}")
            self.set_next_enabled(True)
        else:
            self._detected_path = None
            self.status_icon.setIcon(FluentIcon.SEARCH)
            self._apply_status("未选择路径")

    def _apply_status(self, path: str) -> None:
        self.status_path.setText(path)
        self.status_path.setVisible(bool(path))

    def _browse(self) -> None:
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
        if not exe_path.exists():
            logger.error("选择的路径不存在")
            InfoBar.error(
                title="错误",
                content="选择的路径不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window(),
            )
            return

        InfoBar.info(
            title="信息",
            content="已关闭自动路径获取",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.window(),
        )
        config.ClassIsland.AutoPath = False
        config.ClassIsland.Path = str(exe_path)
        self.status_icon.setIcon(FluentIcon.COMPLETED)
        self._apply_status(f"手动选择: {exe_path}")
        self.set_next_enabled(True)


class FinishNavCard(CardWidget):
    """OOBE 结束页导航卡片：图标 + 标题 + 描述 + 链接图标"""

    def __init__(self, icon, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(86)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(14)

        self.icon_widget = IconWidget(icon, self)
        self.icon_widget.setFixedSize(24, 24)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.title_label = StrongBodyLabel(title, self)
        self.content_label = BodyLabel(content, self)
        self.content_label.setWordWrap(True)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.content_label)

        self.link_icon = IconWidget(FluentIcon.LINK.colored(QColor("#878787"), QColor("#b5b5b5")), self)
        self.link_icon.setFixedSize(16, 16)

        layout.addWidget(self.icon_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self.link_icon, 0, Qt.AlignmentFlag.AlignVCenter)


class FinishStep(OobeStep):
    title = "一切就绪！"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout_instance = QVBoxLayout(self)
        self.layout_instance.setContentsMargins(0, 8, 0, 0)
        self.layout_instance.setSpacing(10)

        self.title_label = BodyLabel("接下来：")
        self.layout_instance.addWidget(self.title_label)

        self.settings_card = FinishNavCard(
            FluentIcon.SETTING,
            "编辑设置",
            "调整更多功能与选项。",
            self,
        )
        self.profile_card = FinishNavCard(
            FluentIcon.DOCUMENT,
            "编辑档案",
            "管理用于登录的希沃账号。",
            self,
        )
        self.settings_card.clicked.connect(lambda: self._open_page(OobeWindow.NAV_CONFIG))
        self.profile_card.clicked.connect(lambda: self._open_page(OobeWindow.NAV_PROFILE))

        self.layout_instance.addWidget(self.settings_card)
        self.layout_instance.addWidget(self.profile_card)

        self.layout_instance.addStretch(1)

    def _open_page(self, target: str) -> None:
        """关闭向导并请求主界面直达指定页面"""
        window = cast("OobeWindow", self.window())
        window.navigate_to = target
        window.accept()
