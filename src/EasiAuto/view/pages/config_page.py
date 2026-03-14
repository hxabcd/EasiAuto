import weakref

from loguru import logger

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QScroller,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ExpandGroupSettingCard,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    PushSettingCard,
    SmoothScrollArea,
    Theme,
    TitleLabel,
    TransparentPushButton,
    setTheme,
)

from EasiAuto.common import utils
from EasiAuto.common.config import ConfigGroup, LoginMethod, config
from EasiAuto.common.consts import IS_FULL
from EasiAuto.view.components import SettingCard
from EasiAuto.view.components.qfw_widgets import SettingCardGroup
from EasiAuto.view.utils import get_main_container, set_enable_by


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
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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
        collapse_card.setVisible(config.Debug.DebugMode)

        # 额外属性
        for name, card in SettingCard.index.items():
            match name:
                case "Login.Method":
                    card.widget.setMinimumWidth(200)
                    if not IS_FULL:  # LITE 版，禁用进程注入登录
                        fixed_index = card.widget.findData(LoginMethod.INJECT)
                        if fixed_index != -1:
                            card.widget.setItemEnabled(fixed_index, False)
                case "Login.SkipOnce":
                    button_card = TransparentPushButton(icon=FluentIcon.SHARE, text="创建快捷方式")
                    button_card.clicked.connect(
                        lambda: utils.create_shortcut(
                            args="skip",
                            name="跳过下次自动登录",
                            show_result_to=get_main_container(),
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
                        icon=FluentIcon.CAMERA, title="录制模式", content="进入录制模式获取坐标", text="不可用"
                    )
                    recoard_card.setEnabled(False)  # TODO: 录制模式
                    card.addGroupWidget(recoard_card)
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
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=get_main_container(),
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
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=get_main_container(),
            )
