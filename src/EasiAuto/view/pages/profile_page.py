"""设置 - 档案页：列表选择器与档案编辑器的组装"""

from __future__ import annotations

from loguru import logger

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidgetItem,
    QScroller,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    CommandBar,
    FluentIcon,
    HorizontalSeparator,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    TitleLabel,
    VerticalSeparator,
    setFont,
)

from EasiAuto.core import security
from EasiAuto.core.utils import create_shortcut
from EasiAuto.integrations.classisland_manager import classisland_manager as ci_manager
from EasiAuto.models.config import config
from EasiAuto.models.profile import BaseAutomation, EasiAutomation, ProfileChangeReason, ProfileLockedError, profile
from EasiAuto.services.binding_service import ClassIslandBindingBackend
from EasiAuto.view.components import ProfileCard, ProfileEditor, ProfileStatusBar
from EasiAuto.view.components.master_password_flyout import show_master_password_flyout
from EasiAuto.view.components.qfw_widgets import ListWidget
from EasiAuto.view.helpers import get_main_container
from EasiAuto.view.tokens import TEXT_SECONDARY_DARK, TEXT_SECONDARY_LIGHT


class ProfileManagePage(QWidget):
    """档案编辑页"""

    profileChanged = Signal()
    runAutomation = Signal(BaseAutomation)

    def __init__(self):
        super().__init__()
        self.current_list_item: QListWidgetItem | None = None
        self.binding_backend = ClassIslandBindingBackend()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # 左侧：档案列表选择器
        self.selector_widget = QWidget()
        self.selector_layout = QVBoxLayout(self.selector_widget)
        self.selector_layout.setContentsMargins(4, 0, 0, 8)

        self.action_bar = CommandBar()
        self.action_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.action_bar.addAction(Action(FluentIcon.ADD, "添加", triggered=self._add_automation))
        self.action_bar.addAction(Action(FluentIcon.SYNC, "刷新", triggered=self._init_selector))

        self.auto_list = ListWidget()
        self.auto_list.setSpacing(3)
        QScroller.grabGesture(self.auto_list.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.selector_layout.addWidget(self.action_bar)
        self.selector_layout.addWidget(self.auto_list)

        # 右侧：档案编辑器
        self.editor = ProfileEditor()

        main_layout.addWidget(self.selector_widget, 1)
        main_layout.addWidget(VerticalSeparator())
        main_layout.addWidget(self.editor, 1)

        layout.addLayout(main_layout, 1)

        self.editor.saveRequested.connect(self._on_editor_save_requested)
        self._init_selector()
        profile.notifier.changed.connect(self._on_profile_model_changed)

    def _sync_bindings(self):
        if not ci_manager:
            return

        # 读取当前 CI 绑定关系并提交，确保档案信息变更后自动化配置同步刷新
        desired_binding_map = self.binding_backend.get_binding_map()
        ok = self.binding_backend.sync(desired_binding_map)

        if not ok:
            errors = self.binding_backend.last_errors
            content = "；".join(errors[:3]) if errors else "请检查 ClassIsland 状态与配置"
            if len(errors) > 3:
                content += "；..."
            InfoBar.error(
                title="同步自动化失败",
                content=content,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=get_main_container(),
            )

    def _init_selector(self):
        self.current_list_item = None
        self.auto_list.clear()
        self.editor.clear()

        for automation in profile.list_automation():
            self._add_automation_item(automation)
        self.refresh_binding_display()

    def _add_automation_item(self, automation: BaseAutomation):
        item = QListWidgetItem(self.auto_list)

        item_widget = ProfileCard(item, automation.id)
        item_widget.itemClicked.connect(self._on_item_clicked)
        item_widget.actionRun.connect(self._handle_action_run)
        item_widget.actionExport.connect(self._handle_action_export)
        item_widget.actionRemove.connect(self._handle_action_remove)
        item_widget.enabledChanged.connect(self._handle_action_enabled_changed)

        self.auto_list.setItemWidget(item, item_widget)
        item.setSizeHint(item_widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, automation)
        return item

    def _add_automation(self):
        self.current_list_item = None
        self.auto_list.clearSelection()
        self.editor.start_new()

    def _on_item_clicked(self, item: QListWidgetItem):
        automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
        self.current_list_item = item
        self.editor.load(automation.model_copy(deep=True))

    def _try_save(self, reason: ProfileChangeReason = "profile_changed") -> bool:
        """保存档案；档案处于锁定态时提示用户先解锁，并返回 False。"""
        try:
            profile.save(reason=reason)
            return True
        except ProfileLockedError:
            InfoBar.warning(
                title="档案已锁定",
                content="请先解锁档案（输入主密码）后再保存",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=get_main_container(),
            )
            return False

    def _on_editor_save_requested(self, automation: BaseAutomation):
        """持久化编辑器提交的档案并刷新界面"""
        profile.upsert_automation(automation)
        if not self._try_save("automation_saved"):
            return

        self._init_selector()

        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            current = item.data(Qt.ItemDataRole.UserRole)
            if current.id == automation.id:
                self.auto_list.setCurrentItem(item)
                self.current_list_item = item
                self.editor.load(current)
                break

        self.profileChanged.emit()

    def _handle_action_run(self, automation_id: str) -> None:
        if not (automation := profile.get_automation(automation_id)):
            logger.error(f"无法找到自动化: {automation_id}")
            return

        self.runAutomation.emit(automation)
        logger.info(f"信号已发送: 运行自动化 {automation.id}")

    def _handle_action_export(self, automation_id: str) -> None:
        if not (automation := profile.get_automation(automation_id)):
            logger.error(f"无法找到自动化: {automation_id}")
            return

        create_shortcut(
            args=f'login --id "{automation.id}" --manual',
            name=automation.export_name,
            icon_name="EasiAutoShortcut",
            show_result_to=get_main_container(),
        )

    def _handle_action_enabled_changed(self, automation_id: str, enabled: bool) -> None:
        if not (automation := profile.get_automation(automation_id)):
            logger.error(f"无法找到自动化: {automation_id}")
            return

        if automation.enabled == enabled:
            return

        automation.enabled = enabled
        if not self._try_save("automation_saved"):
            automation.enabled = not enabled

    def _handle_action_remove(self, item: QListWidgetItem):
        automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
        if profile.delete_automation(automation.id):
            if not self._try_save("automation_deleted"):
                return
            if self.current_list_item == item:
                self.current_list_item = None
                self.editor.clear()
            self.auto_list.takeItem(self.auto_list.row(item))
            self.profileChanged.emit()

    def scroll_to_automation(self, automation_id: str):
        """跳转并选中指定的自动化档案"""
        target_item = None

        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
            if automation and automation.id == automation_id:
                target_item = item
                break

        if target_item:
            self.auto_list.setCurrentItem(target_item)
            self.auto_list.scrollToItem(target_item)

            self._on_item_clicked(target_item)

            logger.info(f"已跳转到档案编辑: {automation_id}")
            return True
        logger.warning(f"跳转失败: 找不到 ID 为 {automation_id} 的档案")
        return False

    def refresh_binding_display(self):
        subject_tags_map = self._build_subject_tags_map()
        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            automation: EasiAutomation | None = item.data(Qt.ItemDataRole.UserRole)
            item_widget = self.auto_list.itemWidget(item)
            if not isinstance(item_widget, ProfileCard) or automation is None:
                continue
            item_widget.update_display(automation)
            item_widget.set_subject_tags(subject_tags_map.get(automation.id, []))

    def _build_subject_tags_map(self) -> dict[str, list[str]]:
        if not ci_manager:
            return {}

        subjects = self.binding_backend.list_subjects()
        subject_name_map = {item.id: item.name for item in subjects if item.id}
        binding_map = self.binding_backend.get_binding_map()

        subject_tags_map: dict[str, list[str]] = {}
        for subject_id, automation_id in binding_map.items():
            if subject_name := subject_name_map.get(subject_id):
                subject_tags_map.setdefault(automation_id, []).append(subject_name)
        return subject_tags_map

    def _on_profile_model_changed(self, reason: ProfileChangeReason):
        if reason in {"automation_saved", "automation_deleted"}:
            self._sync_bindings()
            self.refresh_binding_display()
        elif reason == "encryption_changed":
            # 解锁后密码恢复明文，重建列表以刷新档案数据
            self._init_selector()


class FirstUseSubpage(QWidget):
    """档案页 - 首次使用 子页面（保护密码初始化引导）"""

    setupRequested = Signal()  # 用户点击「设置保护密码」
    dismissed = Signal()  # 用户选择「稍后再说」

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_container = QHBoxLayout()
        icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_icon = IconWidget(FluentIcon.VPN)
        hint_icon.setFixedSize(96, 96)
        icon_container.addWidget(hint_icon)

        hint_label = TitleLabel("设置密码保护")
        hint_desc = BodyLabel("设置用于加密登录信息的密码，保护账号隐私安全")
        setFont(hint_desc, 15)
        hint_desc2 = CaptionLabel("忘记后将无法找回，请牢记密码")
        hint_desc2.setTextColor(QColor(TEXT_SECONDARY_LIGHT), QColor(TEXT_SECONDARY_DARK))
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_desc2.setAlignment(Qt.AlignmentFlag.AlignCenter)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        setup_button = PrimaryPushButton(icon=FluentIcon.VPN, text="设置保护密码")
        setup_button.setFixedWidth(150)
        setup_button.clicked.connect(self.setupRequested.emit)
        self.setup_button = setup_button

        dismiss_button = PushButton(icon=FluentIcon.RIGHT_ARROW, text="暂不设置")
        dismiss_button.setFixedWidth(150)
        dismiss_button.clicked.connect(self.dismissed.emit)

        actions_layout.addWidget(setup_button)
        actions_layout.addWidget(dismiss_button)

        layout.addLayout(icon_container)
        layout.addSpacing(12)
        layout.addWidget(hint_label)
        layout.addWidget(hint_desc)
        layout.addWidget(hint_desc2)
        layout.addSpacing(18)
        layout.addLayout(actions_layout)


class ProfileLockedOverlay(QWidget):
    """档案页 - 锁定覆盖层：需要先输主密码才能查看档案密码时展示"""

    unlockRequested = Signal()  # 用户点击「解锁档案」

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_container = QHBoxLayout()
        icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_icon = IconWidget(FluentIcon.FINGERPRINT)
        hint_icon.setFixedSize(96, 96)
        icon_container.addWidget(hint_icon)

        hint_label = TitleLabel("档案已锁定")
        hint_desc = BodyLabel("档案已使用主密码加密，解锁后才能查看与编辑登录信息")
        setFont(hint_desc, 15)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        unlock_button = PrimaryPushButton(icon=FluentIcon.VPN, text="解锁档案")
        unlock_button.setFixedWidth(150)
        unlock_button.clicked.connect(self.unlockRequested.emit)

        layout.addLayout(icon_container)
        layout.addSpacing(12)
        layout.addWidget(hint_label)
        layout.addWidget(hint_desc)
        layout.addSpacing(18)
        layout.addWidget(unlock_button, alignment=Qt.AlignmentFlag.AlignHCenter)


class ProfilePage(QWidget):
    """设置 - 档案页"""

    profileChanged = Signal()
    runAutomation = Signal(BaseAutomation)

    def __init__(self):
        super().__init__()
        logger.debug("初始化档案页")
        self.setObjectName("ProfilePage")
        self.setStyleSheet("border: none; background-color: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.status_bar = ProfileStatusBar()
        self.manager_page = ProfileManagePage()
        self.manager_page.profileChanged.connect(self.profileChanged.emit)
        self.manager_page.runAutomation.connect(self.runAutomation.emit)

        # 首次使用引导页（保护密码初始化），仅首次打开档案页时展示
        self.first_use_page = FirstUseSubpage()
        self.first_use_page.setupRequested.connect(self._on_setup_master_password)
        self.first_use_page.dismissed.connect(self._dismiss_first_use)

        # 锁定覆盖层：查看密码前需先输主密码时，用它替换管理页
        self.locked_page = ProfileLockedOverlay()
        self.locked_page.unlockRequested.connect(self._on_unlock_requested)
        # 本次启动内是否已输主密码查看过（用于「免密查看」关闭时只拦一次）
        self._profile_view_unlocked = False

        self.main_widget = QStackedWidget()
        self.main_widget.addWidget(self.first_use_page)
        self.main_widget.addWidget(self.manager_page)
        self.main_widget.addWidget(self.locked_page)

        self.separator = HorizontalSeparator()
        layout.addWidget(self.status_bar)
        layout.addWidget(self.separator)
        layout.addWidget(self.main_widget)

        profile.notifier.changed.connect(self._on_profile_notifier_changed)
        self._refresh_view()

    def _is_first_use(self) -> bool:
        """引导未展示过时进入首次使用页"""
        return not config.Internal.IsProfilePageNoticeShown

    def _is_locked(self) -> bool:
        """档案需先输主密码才能查看密码时返回 True（锁定覆盖层）"""
        if not profile.encryption_enabled:
            return False
        if not security.is_master_key_unlocked():
            # 会话未解锁：无论如何需要先解锁会话
            return True
        if profile.passwordless_view:
            return False
        # 未勾选「免密查看」：本次启动内需先输主密码查看一次
        return not self._profile_view_unlocked

    def _refresh_view(self):
        if self._is_locked():
            self.main_widget.setCurrentWidget(self.locked_page)
            # 保留「高级选项」入口，便于调整免密查看/加密
            self.status_bar.set_compact_mode(False)
            return
        is_first_use = self._is_first_use()
        self.main_widget.setCurrentWidget(self.first_use_page if is_first_use else self.manager_page)
        # 引导页状态栏仅保留左侧标题，隐藏右侧按钮与状态提示
        self.status_bar.set_compact_mode(is_first_use)

    def _on_profile_notifier_changed(self, reason: ProfileChangeReason):
        if reason == "encryption_changed":
            self._refresh_view()

    def _on_unlock_requested(self):
        """锁定覆盖层点击「解锁档案」：弹出模态主密码对话框解锁"""
        from EasiAuto.view.components.master_password_dialog import MasterPasswordDialog

        dialog = MasterPasswordDialog(
            title="解锁档案",
            description="档案已使用主密码加密，请输入主密码以查看档案密码",
            verify=profile.unlock_master_password,
            parent=self.window(),
        )
        dialog.exec()
        if dialog.get_password() is not None:
            self._profile_view_unlocked = True
            self._refresh_view()

    def _dismiss_first_use(self):
        """结束首次使用引导，切换到档案管理页"""
        config.Internal.IsProfilePageNoticeShown = True
        self._refresh_view()

    def _on_setup_master_password(self):
        """引导页点击「设置保护密码」：弹出主密码设置 Flyout"""
        show_master_password_flyout(
            target=self.first_use_page.setup_button,
            parent=self,
            title="设置主密码",
            description="设置用于加密登录信息的主密码，保护账号隐私安全。忘记后将无法找回，请牢记密码",
            require_confirm=True,
            confirm_text="启用加密",
            on_confirm=self._apply_setup_master_password,
        )

    def _apply_setup_master_password(self, master_password: str) -> str | None:
        try:
            profile.enable_encryption(master_password)
        except Exception as e:
            logger.error(f"启用档案加密失败: {e}")
            return "启用加密失败，请重试"
        self._dismiss_first_use()
        return None

    def open_automation_editor(self, automation_id: str):
        """跳过引导并跳转到指定档案编辑（外部导航入口）"""
        if self._is_first_use():
            self._dismiss_first_use()
        self.manager_page.scroll_to_automation(automation_id)
