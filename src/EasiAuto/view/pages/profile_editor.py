from __future__ import annotations

import hashlib
from io import BytesIO

import requests
from loguru import logger
from PIL import Image

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QListWidgetItem,
    QScroller,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    AvatarWidget,
    BodyLabel,
    CardWidget,
    CommandBar,
    FluentIcon,
    HorizontalSeparator,
    IconInfoBadge,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBoxBase,
    PasswordLineEdit,
    PrimaryPushButton,
    SubtitleLabel,
    SwitchButton,
    TransparentPushButton,
    VerticalSeparator,
)

from EasiAuto.automation.easinote_api import (
    SeewoAuthError,
    SeewoClient,
    SeewoLoginError,
    SeewoNeedCaptcha,
    SeewoNetworkError,
)
from EasiAuto.consts import AVATAR_DIR
from EasiAuto.core.utils import create_shortcut
from EasiAuto.integrations.classisland_manager import classisland_manager as ci_manager
from EasiAuto.models.profile import BaseAutomation, EasiAutomation, ProfileChangeReason, profile
from EasiAuto.services.binding_service import ClassIslandBindingBackend
from EasiAuto.view.components import SettingCard, SettingCardType
from EasiAuto.view.components.qfw_widgets import ListWidget, PillOverflowBar, PillPushButton
from EasiAuto.view.helpers import get_main_container, get_main_window


class AdvancedOptionsDialog(MessageBoxBase):
    """高级选项"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("高级选项", self)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)

        # 初始化设置项
        self._init_settings()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(12)
        self.viewLayout.addWidget(self.view)

        self.widget.setMinimumWidth(400)
        self.yesButton.setText("关闭")
        self.yesButton.clicked.connect(self.accept)
        self.cancelButton.hide()

    def _init_settings(self):
        """初始化设置项"""
        self.encrypt_card = SettingCard(
            card_type=SettingCardType.SWITCH,
            icon=FluentIcon.VPN,
            title="启用档案密码加密",
            content="保存档案时对密码加密",
            is_item=True,
            item_margin=False,
        )
        self.encrypt_card.setChecked(profile.encryption_enabled)
        self.encrypt_card.valueChanged.connect(self._on_encryption_changed)
        self.vBoxLayout.addWidget(self.encrypt_card)

    def _on_encryption_changed(self, checked: bool):
        profile.encryption_enabled = checked
        profile.save(reason="encryption_changed")


class ProfileStatusBar(QWidget):
    """档案页状态栏"""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(54)

        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(16, 0, 16, 0)

        self.option_button = TransparentPushButton(icon=FluentIcon.DEVELOPER_TOOLS, text="高级选项")
        self.option_button.clicked.connect(self._show_advanced_options)

        layout.addWidget(SubtitleLabel("档案编辑"))
        layout.addStretch(1)
        layout.addWidget(self.option_button)

    def _show_advanced_options(self):
        dialog = AdvancedOptionsDialog(self.window())
        dialog.exec()


class _UserAuthVerificationThread(QThread):
    """后台线程：校验希沃账号密码，并缓存头像。"""

    succeeded = Signal(str, str)  # account_name, avatar_path
    failed = Signal(str)  # 认证失败原因
    offline = Signal(str)  # 网络异常（跳过校验）

    def __init__(self, account: str, password: str, parent=None):
        super().__init__(parent)
        self._account = account
        self._password = password

    def run(self) -> None:
        try:
            with SeewoClient() as client:
                result = client.login(self._account, self._password)
        except SeewoNetworkError as e:
            self.offline.emit(str(e))
            return
        except SeewoNeedCaptcha as e:
            self.failed.emit(str(e))
            return
        except (SeewoAuthError, SeewoLoginError) as e:
            self.failed.emit(str(e))
            return

        avatar_path = self._download_avatar(result.user.photo_url or None)
        account_name = result.user.nick_name or result.user.real_name
        self.succeeded.emit(account_name, avatar_path or "")

    @staticmethod
    def _download_avatar(url: str | None) -> str | None:
        """下载头像到本地缓存并返回文件路径，失败或不存在返回 None"""
        if not url:
            return None
        try:
            response = requests.get(url, timeout=15)
            if response.status_code != 200:
                return None
            image = Image.open(BytesIO(response.content))
            image.load()
        except Exception as e:
            logger.warning(f"头像下载失败: {e}")
            return None

        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = AVATAR_DIR / f"{hashlib.md5(url.encode('utf-8')).hexdigest()}.png"
        try:
            image.save(cache_path, format="PNG")
        except OSError as e:
            logger.warning(f"头像保存失败: {e}")
            return None
        return str(cache_path)


class ProfileCard(CardWidget):
    """档案卡片"""

    itemClicked = Signal(QListWidgetItem)
    actionRun = Signal(str)  # automation_id
    actionExport = Signal(str)  # automation_id
    actionRemove = Signal(QListWidgetItem)
    enabledChanged = Signal(str, bool)  # automation_id, enabled

    def __init__(self, item: QListWidgetItem, automation_id: str | None = None):
        super().__init__()
        self.list_item = item
        self._automation_id = automation_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 上半区域：头像 + 信息
        self.info_container = QWidget()
        info_layout = QHBoxLayout(self.info_container)
        info_layout.setContentsMargins(16, 16, 16, 16)
        info_layout.setSpacing(14)

        self.avatar_label = AvatarWidget()
        self.avatar_label.setRadius(32)
        if self.automation:
            if img := getattr(self.automation, "avatar", None):
                self.avatar_label.setImage(img)
            elif name := self.automation.display_name:
                self.avatar_label.setText(name[0].upper())
        else:
            self.avatar_label.setText("?")

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self.name_label = SubtitleLabel(self.automation.display_name or "未命名自动化")
        self.detail_label = BodyLabel(self.automation.detail_name)
        self.detail_label.setTextColor(QColor("#878787"), QColor("#b5b5b5"))

        self.subject_bar = PillOverflowBar()
        self.subject_bar.setContentsMargins(0, 6, 0, 0)
        self.subject_bar.setSpacing(6)

        self.add_subject_button = PillPushButton("添加", icon=FluentIcon.ADD)
        self.add_subject_button.clicked.connect(self._on_add_subject)
        self.subject_bar.setLastWidget(self.add_subject_button)

        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.detail_label)
        text_layout.addWidget(self.subject_bar)

        info_layout.addWidget(self.avatar_label)
        info_layout.addLayout(text_layout, 1)

        # 下半区域：动作栏
        self.action_container = QWidget()
        action_layout = QHBoxLayout(self.action_container)
        action_layout.setContentsMargins(12, 4, 12, 4)
        action_layout.setSpacing(0)

        self.command_bar = CommandBar()
        self.command_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.action_run = Action(
            FluentIcon.PLAY,
            "运行",
            triggered=self._on_run,
        )
        self.action_export = Action(
            FluentIcon.SHARE,
            "导出",
            triggered=self._on_export,
        )
        self.action_remove = Action(
            FluentIcon.CANCEL_MEDIUM,
            "删除",
            triggered=lambda: self.actionRemove.emit(self.list_item),
        )

        self.command_bar.addAction(self.action_run)
        self.command_bar.addAction(self.action_export)
        self.command_bar.addAction(self.action_remove)

        self.enabled_switch = SwitchButton()
        self.enabled_switch.setOnText("启用")
        self.enabled_switch.setOffText("禁用")
        self.enabled_switch.setChecked(self.automation.enabled if self.automation else False)
        self.enabled_switch.checkedChanged.connect(self._on_enabled_changed)

        action_layout.addWidget(self.command_bar, 1)
        action_layout.addWidget(self.enabled_switch, alignment=Qt.AlignmentFlag.AlignRight)
        action_layout.addSpacing(6)

        layout.addWidget(self.info_container)
        layout.addWidget(HorizontalSeparator())
        layout.addWidget(self.action_container)

        self.setMouseTracking(True)
        if self.automation:
            self.update_display(self.automation)

    @property
    def automation(self) -> BaseAutomation:
        if not self._automation_id:
            raise ValueError("未设置 automation_id")

        automation: BaseAutomation | None = self.list_item.data(Qt.ItemDataRole.UserRole)
        if automation and automation.id == self._automation_id:
            return automation

        if automation := profile.get_automation(self._automation_id):
            return automation

        raise ValueError(f"无法找到对应的自动化: {self._automation_id}")

    def _update_subjects(self, tags: list[str]):
        self.subject_bar.setTags(tags)

    def _on_add_subject(self):
        # TODO: 跳转至对应科目
        window = get_main_window()
        window.switchTo(window.automation_page)

    def _on_run(self):
        if self._automation_id:
            self.actionRun.emit(self._automation_id)

    def _on_export(self):
        if self._automation_id:
            self.actionExport.emit(self._automation_id)

    def update_display(self, automation: BaseAutomation):
        self._automation_id = automation.id
        self.name_label.setText(self.automation.display_name or "未命名自动化")
        self.detail_label.setText(self.automation.detail_name or "")
        self.enabled_switch.setChecked(automation.enabled)
        self.detail_label.setText(self.automation.detail_name or "")

        if img := getattr(self.automation, "avatar", None):
            try:
                self.avatar_label.setImage(str(img))
            except Exception:
                self.avatar_label.setText(self.automation.display_name[:1] if self.automation.display_name else "?")
        elif name := self.automation.display_name:
            self.avatar_label.setText(name[0].upper())
        else:
            self.avatar_label.setText("?")

    def set_subject_tags(self, tags: list[str]):
        self._update_subjects(tags)

    def _on_enabled_changed(self, enabled: bool):
        if self._automation_id:
            self.enabledChanged.emit(self._automation_id, enabled)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.itemClicked.emit(self.list_item)
        super().mousePressEvent(e)


class ProfileManagePage(QWidget):
    """档案编辑页"""

    profileChanged = Signal()
    runAutomation = Signal(BaseAutomation)

    def __init__(self):
        super().__init__()
        self.current_automation: BaseAutomation | None = None
        self.current_list_item: QListWidgetItem | None = None
        self.is_new_automation = False
        self._pending_save_automation: BaseAutomation | None = None
        self.binding_backend = ClassIslandBindingBackend()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

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

        self.editor_widget = QWidget()
        self.editor_layout = QVBoxLayout(self.editor_widget)

        self.new_auto_hint = CardWidget()
        self.new_auto_hint.setFixedHeight(44)
        hint_layout = QHBoxLayout(self.new_auto_hint)
        hint_layout.setContentsMargins(12, 2, 12, 2)
        hint_icon = IconInfoBadge.attension(FluentIcon.RINGER)
        hint_icon.setFixedSize(24, 24)
        hint_icon.setIconSize(QSize(12, 12))
        hint_text = BodyLabel("正在编辑新档案")
        hint_layout.addWidget(hint_icon)
        hint_layout.addWidget(hint_text)
        self.new_auto_hint.hide()

        self.automation_name_label = SubtitleLabel()

        self.form = QWidget()
        self.form.setStyleSheet("QLabel { font-size: 14px; margin-right: 4px; }")
        form_layout = QFormLayout(self.form)

        self.name_edit = LineEdit()
        self.account_edit = LineEdit()
        self.password_edit = PasswordLineEdit()

        form_layout.addRow(BodyLabel("名称 (可选)"), self.name_edit)
        form_layout.addRow(BodyLabel("账号"), self.account_edit)
        form_layout.addRow(BodyLabel("密码"), self.password_edit)

        self.save_button = PrimaryPushButton("保存")
        self.save_button.clicked.connect(self._handle_save_automation)

        self.editor_layout.addWidget(self.new_auto_hint)
        self.editor_layout.addWidget(self.automation_name_label)
        self.editor_layout.addWidget(self.form)
        self.editor_layout.addStretch(1)
        self.editor_layout.addWidget(self.save_button)

        self.editor_widget.setDisabled(True)

        main_layout.addWidget(self.selector_widget, 1)
        main_layout.addWidget(VerticalSeparator())
        main_layout.addWidget(self.editor_widget, 1)

        layout.addLayout(main_layout, 1)

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
        self._clear_editor()

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
        self.is_new_automation = True
        self.current_automation = EasiAutomation(account="", password="")
        self.current_list_item = None
        self.auto_list.clearSelection()
        self._update_editor(self.current_automation)
        self.editor_widget.setEnabled(True)

    def _display_name(self, automation: BaseAutomation) -> str:
        return automation.name or "未命名档案"

    def _update_editor(self, automation: BaseAutomation):
        self.current_automation = automation
        self.new_auto_hint.setVisible(self.is_new_automation)
        self.automation_name_label.setText(self._display_name(automation))

        self.name_edit.setText(automation.name or "")
        match automation:
            case EasiAutomation():
                self.account_edit.setText(automation.account)
                self.password_edit.setText(automation.password)
                self.account_edit.setDisabled(False)
                self.password_edit.setDisabled(False)

        self.editor_widget.setEnabled(True)

    def _clear_editor(self):
        self.new_auto_hint.hide()
        self.automation_name_label.setText("")
        self.name_edit.clear()
        self.account_edit.clear()
        self.password_edit.clear()
        self.account_edit.setEnabled(True)
        self.password_edit.setEnabled(True)
        self.editor_widget.setDisabled(True)

    def _save_form(self) -> tuple[str, str]:
        """收集表单并校验，返回 (账号, 密码)"""
        if not self.current_automation:
            raise ValueError("未选择档案")

        self.current_automation.name = self.name_edit.text().strip() or None

        if isinstance(self.current_automation, EasiAutomation):
            account = self.account_edit.text().strip()
            password = self.password_edit.text()

            if account == "":
                raise ValueError("账号不能为空")
            if password == "":
                raise ValueError("密码不能为空")

            existing = next(
                (
                    item
                    for item in profile.list_automation()
                    if isinstance(item, EasiAutomation) and item.account == account
                ),
                None,
            )
            if existing and existing.id != self.current_automation.id:
                raise ValueError("账号已存在")

            self.current_automation.account = account
            self.current_automation.password = password

            return account, password
        return "", ""

    def _commit_save(self):
        """将当前档案写入 profile 并刷新界面"""
        automation = self.current_automation
        if automation is None:
            return
        profile.upsert_automation(automation)
        profile.save(reason="automation_saved")

        self.is_new_automation = False
        self._init_selector()

        for i in range(self.auto_list.count()):
            item = self.auto_list.item(i)
            current = item.data(Qt.ItemDataRole.UserRole)
            if current.id == automation.id:
                self.auto_list.setCurrentItem(item)
                self.current_list_item = item
                self._update_editor(current)
                break

        self.profileChanged.emit()

    def _handle_save_automation(self):
        try:
            account, password = self._save_form()
        except ValueError as e:
            InfoBar.error(
                title="保存失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=get_main_container(),
            )
            return
        except Exception as e:
            logger.exception("保存档案时发生异常")
            InfoBar.error(
                title="保存失败",
                content=f"发生未知错误: {e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=get_main_container(),
            )
            return

        # 无账号密码（非账密档案）直接保存
        if not account:
            self._commit_save()
            return

        # 后台校验账号密码，成功或离线时再保存
        self._pending_save_automation = self.current_automation
        self.save_button.setEnabled(False)
        self.save_button.setText("校验中…")

        worker = _UserAuthVerificationThread(account, password, parent=self)
        worker.succeeded.connect(self._on_auth_succeeded)
        worker.failed.connect(self._on_auth_failed)
        worker.offline.connect(self._on_auth_offline)
        worker.finished.connect(self._on_auth_thread_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _resolve_pending_save(self) -> EasiAutomation | None:
        """校验期间用户切换了编辑对象则放弃保存，返回待保存档案"""
        if self.current_automation is not self._pending_save_automation:
            logger.warning("校验期间编辑对象已切换，放弃本次保存")
            InfoBar.error(
                title="保存已取消",
                content="账号校验期间已切换档案，请重新保存",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=get_main_container(),
            )
            self._pending_save_automation = None
            return None

        automation = self.current_automation
        assert isinstance(automation, EasiAutomation)
        self._pending_save_automation = None
        return automation

    def _on_auth_succeeded(self, account_name: str, avatar_path: str):
        automation = self._resolve_pending_save()
        if automation is None:
            return
        automation.account_name = account_name or None
        automation.avatar = avatar_path or None
        self._commit_save()

    def _on_auth_failed(self, message: str):
        InfoBar.error(
            title="账号校验失败",
            content=f"未保存档案：{message}",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=4000,
            parent=get_main_container(),
        )

    def _on_auth_offline(self, message: str):
        logger.warning(f"离线环境，跳过账号校验: {message}")
        if self._resolve_pending_save() is not None:
            self._commit_save()

    def _on_auth_thread_finished(self):
        self.save_button.setEnabled(True)
        self.save_button.setText("保存")

    def _on_item_clicked(self, item: QListWidgetItem):
        automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
        self.current_list_item = item
        self.is_new_automation = False
        self._update_editor(automation.model_copy(deep=True))

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
            show_result_to=get_main_container(),
        )

    def _handle_action_enabled_changed(self, automation_id: str, enabled: bool) -> None:
        if not (automation := profile.get_automation(automation_id)):
            logger.error(f"无法找到自动化: {automation_id}")
            return

        if automation.enabled == enabled:
            return

        automation.enabled = enabled
        profile.save(reason="automation_saved")

    def _handle_action_remove(self, item: QListWidgetItem):
        automation: EasiAutomation = item.data(Qt.ItemDataRole.UserRole)
        if profile.delete_automation(automation.id):
            profile.save(reason="automation_deleted")
            if self.current_list_item == item:
                self.current_list_item = None
                self.current_automation = None
                self._clear_editor()
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

        layout.addWidget(self.status_bar)
        layout.addWidget(HorizontalSeparator())
        layout.addWidget(self.manager_page)
