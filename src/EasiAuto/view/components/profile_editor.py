"""档案编辑器组件：表单编辑、账号校验与保存请求"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from loguru import logger

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon,
    IconInfoBadge,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PasswordLineEdit,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
    TransparentToolButton,
)

from EasiAuto.consts import AVATAR_DIR
from EasiAuto.models.config import config
from EasiAuto.models.profile import BaseAutomation, EasiAutomation, ProfileLockedError, profile
from EasiAuto.view.helpers import get_main_container, set_tooltip

from .auth_verification import UserAuthVerificationThread


class ProfileEditor(QWidget):
    """档案编辑器：负责表单编辑、保存校验与保存请求"""

    saveRequested = Signal(BaseAutomation)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.current_automation: BaseAutomation | None = None
        self.is_new_automation = False
        self._pending_save_automation: BaseAutomation | None = None

        layout = QVBoxLayout(self)

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
        self.refresh_button = TransparentToolButton(FluentIcon.SYNC, self)
        set_tooltip(self.refresh_button, "连接希沃白板并刷新用户信息")
        self.refresh_button.clicked.connect(self._on_refresh_user_info)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(8)
        name_row.addWidget(self.automation_name_label)
        name_row.addStretch(1)
        name_row.addWidget(self.refresh_button)

        form = QWidget()
        form.setContentsMargins(0, 0, 0, 0)
        form_layout = QFormLayout(form)
        self.setStyleSheet("BodyLabel { margin-right: 8px; }")

        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("可选")
        self.name_edit.setClearButtonEnabled(True)
        self.account_edit = LineEdit()
        self.password_edit = PasswordLineEdit()

        form_layout.addRow(BodyLabel("账号"), self.account_edit)
        form_layout.addRow(BodyLabel("密码"), self.password_edit)
        form_layout.addRow(BodyLabel("备注"), self.name_edit)

        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        self.avatar_button = PushButton("设置头像")
        self.avatar_button.clicked.connect(self._on_set_avatar)
        actions_layout.addWidget(self.avatar_button)
        actions_layout.addStretch(1)

        self.save_button = PrimaryPushButton("保存")
        self.save_button.clicked.connect(self._handle_save)

        layout.addWidget(self.new_auto_hint)
        layout.addLayout(name_row)
        layout.addWidget(form)
        layout.addSpacing(10)
        layout.addLayout(actions_layout)
        layout.addStretch(1)
        layout.addWidget(self.save_button)

        self.setDisabled(True)

    def _display_name(self, automation: BaseAutomation) -> str:
        return automation.name or "未命名档案"

    # ---- 状态与装载 ----

    def load(self, automation: BaseAutomation, is_new: bool = False):
        """装载档案到表单并启用编辑器"""
        self.current_automation = automation
        self.is_new_automation = is_new
        self.new_auto_hint.setVisible(is_new)
        self.automation_name_label.setText(self._display_name(automation))

        self.name_edit.setText(automation.name or "")
        match automation:
            case EasiAutomation():
                self.account_edit.setText(automation.account)
                self.password_edit.setText(automation.password)
                self.account_edit.setDisabled(False)
                self.password_edit.setDisabled(False)

        self.setEnabled(True)
        # 新档案尚未入库，头像无法立即落盘，先禁用
        self.avatar_button.setEnabled(not is_new)

    def start_new(self):
        """开始编辑新档案"""
        self.load(EasiAutomation(account="", password=""), is_new=True)

    def clear(self):
        """清空表单并禁用编辑器"""
        self.current_automation = None
        self.is_new_automation = False
        self._pending_save_automation = None
        self.new_auto_hint.hide()
        self.automation_name_label.setText("")
        self.name_edit.clear()
        self.account_edit.clear()
        self.password_edit.clear()
        self.account_edit.setEnabled(True)
        self.password_edit.setEnabled(True)
        self.setDisabled(True)

    # ---- 保存与校验 ----

    def _collect_form(self) -> tuple[str, str]:
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

    def _handle_save(self):
        try:
            account, password = self._collect_form()
        except ValueError as e:
            self._show_error("保存失败", str(e))
            return
        except Exception as e:
            logger.exception("保存档案时发生异常")
            self._show_error("保存失败", f"发生未知错误: {e}")
            return

        # 无账号密码（非账密档案）直接提交
        if not account:
            self._request_save()
            return

        if config.Profile.SkipVerify:
            self._request_save()
            return

        # 后台校验账号密码，成功或离线时再提交
        self._pending_save_automation = self.current_automation
        self.save_button.setEnabled(False)
        self.save_button.setText("校验中…")

        worker = UserAuthVerificationThread(account, password, parent=self)
        worker.succeeded.connect(self._on_auth_succeeded)
        worker.failed.connect(self._on_auth_failed)
        worker.offline.connect(self._on_auth_offline)
        worker.finished.connect(self._on_auth_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _request_save(self):
        """将当前档案通过信号提交给页面持久化"""
        if self.current_automation is not None:
            self.saveRequested.emit(self.current_automation)

    def _resolve_pending_save(self) -> EasiAutomation | None:
        """校验期间用户切换了编辑对象则放弃保存，返回待保存档案"""
        if self.current_automation is not self._pending_save_automation:
            logger.warning("校验期间编辑对象已切换，放弃本次保存")
            self._show_error("保存已取消", "账号校验期间已切换档案，请重新保存", duration=3000)
            self._pending_save_automation = None
            return None

        automation = self.current_automation
        assert isinstance(automation, EasiAutomation)
        self._pending_save_automation = None
        return automation

    def _on_auth_succeeded(self, account_name: str, avatar_path: str, uid: str):
        automation = self._resolve_pending_save()
        if automation is None:
            return
        self.apply_user_info(account_name, avatar_path, uid)
        self.saveRequested.emit(automation)

    def _on_auth_failed(self, message: str):
        self._show_error("账号校验失败", f"未保存档案：{message}", duration=4000)

    def _on_auth_offline(self, message: str):
        logger.warning(f"离线环境，跳过账号校验: {message}")
        automation = self._resolve_pending_save()
        if automation is not None:
            self.saveRequested.emit(automation)

    def _on_auth_finished(self):
        self.save_button.setEnabled(True)
        self.save_button.setText("保存")

    def apply_user_info(self, account_name: str, avatar_path: str, uid: str):
        """应用希沃用户信息（用户名、头像、uid）到当前档案。

        供保存校验成功与“刷新”按钮公共调用。
        """
        automation = self.current_automation
        if not isinstance(automation, EasiAutomation):
            return
        automation.account_name = account_name or None
        automation.avatar = avatar_path or None
        automation.login_uid = uid or None

    # ---- 刷新 / 头像 / 关联 ----

    def _on_refresh_user_info(self):
        """连接希沃白板刷新当前账号的用户信息（uid、头像）。"""
        automation = self.current_automation
        if not isinstance(automation, EasiAutomation):
            self._show_error("无法刷新", "当前档案不支持连接希沃账号")
            return
        account = self.account_edit.text().strip()
        password = self.password_edit.text()
        if not account or not password:
            self._show_error("无法刷新", "请先填写账号和密码")
            return

        self.refresh_button.setEnabled(False)
        worker = UserAuthVerificationThread(account, password, parent=self)
        worker.succeeded.connect(self._on_refresh_succeeded)
        worker.failed.connect(lambda msg: self._show_error("刷新失败", msg))
        worker.offline.connect(lambda msg: self._show_warning("刷新已跳过", msg))
        worker.finished.connect(self._on_refresh_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_refresh_succeeded(self, account_name: str, avatar_path: str, uid: str):
        self.apply_user_info(account_name, avatar_path, uid)
        self._show_success("已更新用户信息", "已连接希沃白板并刷新账号信息")

    def _on_refresh_finished(self):
        self.refresh_button.setEnabled(True)

    def _on_set_avatar(self):
        """选择本地图片作为档案头像，并立即写入磁盘。"""
        if not isinstance(self.current_automation, EasiAutomation):
            self._show_error("无法设置头像", "当前档案暂不支持自定义头像")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择头像图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*)",
        )
        if not path:
            return
        stored = self._store_avatar_image(path)
        self.current_automation.avatar = stored
        self._persist_avatar(stored)

    def _persist_avatar(self, avatar_path: str) -> bool:
        """仅把头像更改写入磁盘；新档案（尚未入库）仅暂存到编辑对象。"""
        automation = self.current_automation
        existing = profile.get_automation(automation.id) if automation else None
        if not isinstance(existing, EasiAutomation):
            return False
        existing.avatar = avatar_path
        try:
            profile.save(reason="automation_saved")
            return True
        except ProfileLockedError:
            self._show_warning("档案已锁定", "头像更改已暂存，请先解锁档案（输入主密码）后再保存")
            return False

    @staticmethod
    def _store_avatar_image(path: str) -> str:
        """将用户选择的图片复制到头像缓存目录，返回可持久化的路径。"""
        suffix = Path(path).suffix.lower() or ".png"
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        destination = AVATAR_DIR / f"user_{uuid.uuid4().hex}{suffix}"
        shutil.copy2(path, destination)
        return str(destination)

    def _show_success(self, title: str, content: str, duration: int = 2500):
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=get_main_container(),
        )

    def _show_warning(self, title: str, content: str, duration: int = 2500):
        InfoBar.warning(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=get_main_container(),
        )

    def _show_error(self, title: str, content: str, duration: int = 2500):
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=get_main_container(),
        )
