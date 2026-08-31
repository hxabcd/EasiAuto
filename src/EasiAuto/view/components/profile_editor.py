"""档案编辑器组件：表单编辑、账号校验与保存请求"""

from __future__ import annotations

from loguru import logger

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
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
    SubtitleLabel,
)

from EasiAuto.models.profile import BaseAutomation, EasiAutomation, profile
from EasiAuto.view.helpers import get_main_container

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
        self.save_button.clicked.connect(self._handle_save)

        layout.addWidget(self.new_auto_hint)
        layout.addWidget(self.automation_name_label)
        layout.addWidget(self.form)
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
        automation.account_name = account_name or None
        automation.avatar = avatar_path or None
        automation.login_uid = uid or None
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
