import weakref
from typing import cast

from loguru import logger

from PySide6.QtCore import Qt, QThread, Signal
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
    SwitchButton,
    Theme,
    TitleLabel,
    TransparentPushButton,
    setTheme,
)

from EasiAuto.consts import IS_DEV, IS_FULL
from EasiAuto.core import utils
from EasiAuto.models.config import ConfigGroup, LoginMethod, config
from EasiAuto.services.announcement_service import Announcement, announcement_service
from EasiAuto.view.components import AnnouncementCard, ExpandSelectorSettingCard, SettingCard
from EasiAuto.view.components.qfw_widgets import SettingCardGroup
from EasiAuto.view.components.setting_card import CardType
from EasiAuto.view.helpers import get_main_container, set_enable_by

# 从属关系映射: [!]Condition -> Targets
ENABLE_MAPPING: dict[str, str | list[str]] = {
    "!Login.EasiNote.AutoPath": "Login.EasiNote.Path",
    "Warning.Enabled": [
        "Warning.Timeout",
        "Warning.MaxDelays",
        "Warning.DelayTime",
    ],
    "Banner.Enabled": "Banner.Style",
}


class _ElevatedPatchThread(QThread):
    """通过 UAC 提权执行修补/撤销修补的工作线程。

    在非管理员运行的实例中，修补需写入系统目录，必须请求 UAC 提权。
    在工作线程中调用 run_elevated_wait 以避免阻塞 UI 线程（DllPatcher 可能耗时数十秒）。

    Attributes:
        enable: True 表示修补，False 表示撤销修补
        done: 完成信号，参数为 (ok, code, launched) —— ok 操作是否成功，code 子进程退出码，launched 子进程是否成功启动
    """

    done = Signal(bool, int, bool)

    def __init__(self, enable: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.enable = enable

    def run(self) -> None:
        from EasiAuto.core.easinote_patcher import PATCH_OK
        from EasiAuto.core.elevation import run_elevated_wait

        launched, code = run_elevated_wait(f"patch {'--on' if self.enable else '--off'}")
        self.done.emit(launched and code == PATCH_OK, code, launched)


def _patch_error_message(code: int, launched: bool) -> str:
    """根据子进程退出码返回用户可读的错误信息"""
    from EasiAuto.core.easinote_patcher import (
        PATCH_ERR_EASINOTE_NOT_FOUND,
        PATCH_ERR_OPERATION_FAILED,
        PATCH_ERR_UNKNOWN,
    )

    if not launched:
        return "未能取得管理员权限"
    if code == PATCH_ERR_EASINOTE_NOT_FOUND:
        return "未找到希沃白板安装路径"
    if code == PATCH_ERR_OPERATION_FAILED:
        return "文件可能被占用，请关闭希沃白板后重试"
    if code == PATCH_ERR_UNKNOWN:
        return "发生未知错误，请查看日志获取详细信息"
    # 其他非零退出码（如 0/1/2）：程序未能正常执行到 patch 逻辑
    return f"程序异常退出（退出码：{code}），请查看日志获取详细信息"


class ConfigPage(QWidget):
    """设置 - 配置页"""

    def __init__(self):
        super().__init__()
        logger.debug("初始化配置页")

        self.menu_index: weakref.WeakValueDictionary[str, SettingCardGroup] = weakref.WeakValueDictionary()
        self.init_ui()
        self._init_announcement_signals()
        announcement_service.fetch_async()

    def init_ui(self):
        self.setObjectName("ConfigPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = TitleLabel("设置")
        title.setContentsMargins(36, 8, 0, 12)
        layout.addWidget(title)

        # 公告组件
        self.init_announcement_ui(layout)

        # 内容组件
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        layout.addWidget(self.scroll_area)

        self.content_widget = QWidget(self.scroll_area)
        self.scroll_area.setWidget(self.content_widget)

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(40, 0, 40, 20)
        self.content_layout.setSpacing(28)

        # 添加设置组
        self.init_patcher_setting_card(layout)
        for group in config.load_page("SettingsPage"):
            self._add_config_menu(group)  # type: ignore
        self.apply_attachment()

        self.content_layout.addStretch()

    def _init_announcement_signals(self):
        announcement_service.fetch_finished.connect(self._on_announcements_fetched)
        announcement_service.fetch_failed.connect(self._on_announcements_failed)

    def _on_announcements_fetched(self, announcements: object):
        items = cast(list[Announcement], announcements)
        hidden_ids = set(config.Internal.HiddenAnnouncementIds)
        visible_items = [item for item in items if item.id not in hidden_ids][:3]
        self._render_announcements(visible_items)

    def _on_announcements_failed(self, error: str):
        logger.debug(f"设置页公告拉取失败，已静默跳过: {error}")
        self._render_announcements([])

    def _render_announcements(self, announcements: list[Announcement]):
        while self.announcement_layout.count():
            item = self.announcement_layout.takeAt(0)
            widget = item.widget()  # type: ignore
            if widget is not None:
                widget.deleteLater()

        if not announcements:
            self.announcement_container.hide()
            return

        for announcement in announcements:
            self.announcement_layout.addWidget(
                AnnouncementCard(
                    announcement,
                    on_close=self._dismiss_announcement,
                    parent=self.announcement_container,
                )
            )

        self.announcement_container.show()

    def _dismiss_announcement(self, announcement_id: str):
        hidden_ids = set(config.Internal.HiddenAnnouncementIds)
        hidden_ids.add(announcement_id)
        config.Internal.HiddenAnnouncementIds = list(hidden_ids)

        remaining_cards: list[Announcement] = []
        for index in range(self.announcement_layout.count()):
            widget = self.announcement_layout.itemAt(index).widget()  # type: ignore
            if isinstance(widget, AnnouncementCard) and widget.announcement.id != announcement_id:
                remaining_cards.append(widget.announcement)

        self._render_announcements(remaining_cards)

    def init_announcement_ui(self, layout: QVBoxLayout):
        self.announcement_container = QWidget(self)
        self.announcement_container.setContentsMargins(0, 0, 0, 0)
        self.announcement_layout = QVBoxLayout(self.announcement_container)
        self.announcement_layout.setContentsMargins(36, 0, 36, 8)
        self.announcement_layout.setSpacing(8)
        self.announcement_container.hide()
        layout.addWidget(self.announcement_container)

    def init_patcher_setting_card(self, layout: QVBoxLayout):
        card = SettingCard(
            card_type=CardType.SWITCH,
            icon=FluentIcon.CODE,
            title="修补希沃白板",
            content="将登录相关的组件修补至希沃白板",
        )
        widget = cast(SwitchButton, card.widget)
        self.content_layout.insertWidget(0, card)

        from EasiAuto.core.automator.utils import resolve_easinote_path
        from EasiAuto.core.easinote_patcher import is_easinote_patched, patch_easinote, unpatch_easinote
        from EasiAuto.core.elevation import is_admin

        path, _ = resolve_easinote_path()
        if path is None:
            widget.setEnabled(False)
            t = card.contentLabel.text()
            card.contentLabel.setText(f"{t}\n未找到希沃白板路径，暂不可用")
            return

        def on_patch_changed(value: bool):
            widget.setEnabled(False)

            if is_admin() or IS_DEV:  # 开发环境无打包 exe 可提权
                ok = patch_easinote(path) if value else unpatch_easinote(path)
                _finish_patch(value, ok, content=None)
                return

            thread = _ElevatedPatchThread(value, parent=self)
            # 挂到 widget 上持有引用，防止 Python 侧在回调前回收线程对象
            widget._patch_thread = thread  # type: ignore[attr-defined]

            def on_done(ok: bool, code: int, launched: bool):
                if not ok:
                    content = _patch_error_message(code, launched)
                else:
                    content = None
                _finish_patch(value, ok, content=content)

            def on_finished():
                widget._patch_thread = None  # type: ignore[attr-defined]
                thread.deleteLater()

            thread.done.connect(on_done)
            thread.finished.connect(on_finished)
            thread.start()

        def _finish_patch(value: bool, ok: bool, content: str | None):
            """统一处理修补结果：更新配置、失败时回弹开关、恢复可用状态"""
            config.Internal.IsEasiNotePatched = value if ok else not value
            if not ok:
                InfoBar.error(
                    title=f"{'修补' if value else '撤销修补'}失败",
                    content=content or "文件可能被占用，请关闭希沃白板后重试",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
                widget.blockSignals(True)
                widget.setChecked(not value)
                widget.blockSignals(False)
            widget.setEnabled(True)

        widget.setChecked(is_easinote_patched(path))
        widget.checkedChanged.connect(on_patch_changed)

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
                    card = cast(ExpandSelectorSettingCard, card)
                    if not IS_FULL:  # LITE 版，禁用进程注入登录
                        card.setOptionEnabled(LoginMethod.INJECT, False)

                case "Login.SkipOnce":
                    card = cast(SettingCard, card)
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
                    card = cast(ExpandGroupSettingCard, card)
                    self.add_resetter(card, "Login.EasiNote", "希沃白板选项")

                case n if n in [
                    f"Login.EasiNote.{field}" for field in ["Path", "ProcessName", "WindowTitle", "Args", "ExtraKills"]
                ]:
                    card = cast(SettingCard, card)
                    card.widget.setFixedWidth(300)

                case "Login.Timeout":
                    card = cast(ExpandGroupSettingCard, card)
                    self.add_resetter(card, "Login.Timeout", "等待时长")

                case n if n.startswith("Login.Timeout."):
                    card = cast(SettingCard, card)
                    card.widget.setMinimumWidth(160)

                case "Login.Position":
                    card = cast(ExpandGroupSettingCard, card)
                    record_card = PushSettingCard(
                        icon=FluentIcon.CAMERA, title="录制模式", content="进入录制模式获取坐标", text="不可用"
                    )
                    record_card.setEnabled(False)  # TODO: 录制模式
                    card.addGroupWidget(record_card)
                    self.add_resetter(card, "Login.Position", "位置坐标")
                case "Banner.Style":
                    card = cast(ExpandGroupSettingCard, card)
                    self.add_resetter(card, "Banner.Style", "横幅样式")

                case "Banner.Style.Text":
                    card = cast(SettingCard, card)
                    card.widget.setFixedWidth(420)

                case "Banner.Style.TextFont":
                    card = cast(SettingCard, card)
                    card.widget.setFixedWidth(200)
                    card.widget.setClearButtonEnabled(True)  # type: ignore

                case "App.LogLevel":
                    card = cast(SettingCard, card)
                    card.widget.setMinimumWidth(104)

                case "App.Theme":
                    card = cast(SettingCard, card)
                    card.valueChanged.connect(lambda t: setTheme(Theme(t.value)))

        # 从属关系
        for condition, _targets in ENABLE_MAPPING.items():
            targets = _targets if isinstance(_targets, list) else [_targets]
            set_enable_by(
                switch=SettingCard.index[condition.removeprefix("!")].widget,  # type: ignore
                widgets=[SettingCard.index[t] for t in targets],
                reverse=condition.startswith("!"),
            )

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
