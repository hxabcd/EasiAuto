from __future__ import annotations

from typing import cast

from loguru import logger
from qframelesswindow import FramelessDialog

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon,
    FluentStyleSheet,
    InfoBar,
    InfoBarPosition,
    PipsPager,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
)

from EasiAuto.core.utils import get_resource
from EasiAuto.models.config import config


class OobeStep(QWidget):
    """OOBE 步骤基类

    子类通过类属性声明元信息，并按需覆写生命周期钩子：

    Attributes:
        title: 步骤标题，显示在内容区顶部
        skippable: 是否允许跳过此步（显示"跳过此步"按钮）
    """

    title: str = ""
    skippable: bool = False

    def on_enter(self) -> None:
        """进入步骤时调用"""

    def on_leave(self) -> None:
        """离开步骤时调用"""

    def validate(self) -> str | None:
        """点击下一步时的同步校验，返回错误文本则阻止前进"""
        return None

    def commit(self) -> bool:
        """点击下一步时提交本步骤（如执行修补、保存档案）。

        返回 True 表示已完成可立即前进；返回 False 表示提交中或失败，
        步骤需在完成后自行调用向导的 advance() 前进。
        """
        return True

    def set_busy(self, busy: bool, text: str | None = None) -> None:
        """禁用导航按钮，可选地修改下一步文案（转发至向导窗口）"""
        cast("OobeWindow", self.window()).set_busy(busy, text)

    def set_next_enabled(self, enabled: bool, text: str | None = None) -> None:
        """启用/禁用"下一步"按钮，保留上一步与跳过按钮（转发至向导窗口）"""
        cast("OobeWindow", self.window()).set_next_enabled(enabled, text)


class OobeWindow(FramelessDialog):
    """首次运行设置向导窗口"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setResizeEnabled(False)
        self.titleBar.closeBtn.hide()
        # self.setTitleBar(SplitTitleBar(self))
        FluentStyleSheet.DIALOG.apply(self)

        self.setWindowTitle("EasiAuto 设置向导")
        self.setWindowIcon(QIcon(get_resource("icons/EasiAuto.ico")))
        self.setFixedSize(720, 500)

        self.steps: list[OobeStep] = []
        self.current_index: int = 0

        self._init_ui()
        self._init_steps()
        logger.debug("OOBE 向导已初始化")

    def _init_steps(self):
        """组装向导步骤序列"""
        from EasiAuto.view.oobe.steps import (
            BasicStep,
            ClassIslandStep,
            FinishStep,
            LoginMethodStep,
            PatchStep,
            SystemStep,
            ThemeStep,
            WelcomeStep,
        )

        self.set_steps(
            [
                WelcomeStep(),
                BasicStep(),
                ThemeStep(),
                LoginMethodStep(),
                PatchStep(),
                SystemStep(),
                ClassIslandStep(),
                FinishStep(),
            ]
        )

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(12)

        # 步骤标题 + 进度点
        header = QHBoxLayout()
        header.setContentsMargins(24, 0, 24, 0)
        header.setSpacing(12)
        self.titleLabel = SubtitleLabel()
        self.pipsPager = PipsPager(Qt.Orientation.Horizontal)
        self.pipsPager.setSelectionRectVisible(False)
        self.pipsPager.setDisabled(True)
        header.addWidget(self.titleLabel)
        header.addStretch(1)
        header.addWidget(self.pipsPager, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        # 步骤内容
        self.stackedWidget = QStackedWidget()
        self.stackedWidget.setContentsMargins(36, 0, 36, 0)
        layout.addWidget(self.stackedWidget, 1)

        # 底部按钮行
        button_group = QFrame(self)
        button_group.setObjectName("buttonGroup")
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.setContentsMargins(32, 20, 32, 20)
        self.skipWizardButton = PushButton(FluentIcon.CLOSE, "跳过向导")
        self.skipWizardButton.clicked.connect(self._skip_wizard)
        self.skipStepButton = PushButton(FluentIcon.CHEVRON_RIGHT, "跳过此步")
        self.skipStepButton.clicked.connect(self._skip_step)
        self.prevButton = PushButton(FluentIcon.LEFT_ARROW, "上一步")
        self.prevButton.clicked.connect(self._prev)
        self.nextButton = PrimaryPushButton(FluentIcon.RIGHT_ARROW, "下一步")
        self.nextButton.clicked.connect(self._next)
        button_layout.addWidget(self.skipWizardButton)
        button_layout.addWidget(self.skipStepButton)
        button_layout.addStretch(1)
        button_layout.addWidget(self.prevButton)
        button_layout.addWidget(self.nextButton)

        button_group.setLayout(button_layout)
        layout.addWidget(button_group)

    def set_steps(self, steps: list[OobeStep]):
        """设置向导步骤序列并进入第一步"""
        self.steps = steps
        for step in steps:
            self.stackedWidget.addWidget(step)
        self.pipsPager.setPageNumber(len(steps))
        self.pipsPager.setFixedSize(QSize(len(steps) * 16, 16))
        self._switch_to(0)

    # ---------- 导航 ----------

    def current_step(self) -> OobeStep:
        return self.steps[self.current_index]

    def _switch_to(self, index: int):
        """切换到指定步骤并刷新界面状态"""
        self.current_step().on_leave()
        self.current_index = index
        step = self.current_step()
        self.stackedWidget.setCurrentIndex(index)
        self.pipsPager.setCurrentIndex(index)
        self.titleLabel.setText(step.title)
        is_first = index == 0
        is_last = index == len(self.steps) - 1
        self.prevButton.setEnabled(not is_first)
        self.skipStepButton.setVisible(step.skippable and not is_last)
        self.skipWizardButton.setVisible(not is_last)
        self.nextButton.setText("完成" if is_last else "下一步")
        self.nextButton.setIcon(FluentIcon.ACCEPT_MEDIUM if is_last else FluentIcon.RIGHT_ARROW)
        step.on_enter()

    def advance(self):
        """前进到下一步；已在最后一步则关闭向导

        供异步提交的步骤（修补、档案校验）在完成后回调。
        """
        if self.current_index >= len(self.steps) - 1:
            self.accept()
        else:
            self._switch_to(self.current_index + 1)

    def set_busy(self, busy: bool, text: str | None = None):
        """提交期间禁用导航按钮，可选地修改下一步按钮文案"""
        for button in (self.prevButton, self.nextButton, self.skipStepButton, self.skipWizardButton):
            button.setEnabled(not busy)
        self.nextButton.setText(text or ("开始使用" if self.current_index == len(self.steps) - 1 else "下一步"))

    def set_next_enabled(self, enabled: bool, text: str | None = None):
        """启用/禁用"下一步"按钮，不阻塞上一步/跳过

        Args:
            enabled: True 启用，False 禁用
            text: 修改"下一步"按钮文案；启用且未指定时恢复默认文案
        """
        self.nextButton.setEnabled(enabled)
        if text is not None:
            self.nextButton.setText(text)
        elif enabled:
            self.nextButton.setText("开始使用" if self.current_index == len(self.steps) - 1 else "下一步")

    def _prev(self):
        if self.current_index > 0:
            self._switch_to(self.current_index - 1)

    def _next(self):
        step = self.current_step()
        if self.current_index < len(self.steps) - 1:
            error = step.validate()
            if error:
                InfoBar.error(
                    title="无法继续",
                    content=error,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
                return
        if step.commit():
            self.advance()

    def _skip_step(self):
        """跳过当前步骤（不提交）"""
        self.advance()

    def _skip_wizard(self):
        """跳过整个向导，直接进入主界面"""
        logger.info("用户跳过了 OOBE 向导")
        self.accept()

    def accept(self) -> None:
        """OOBE 完成时执行快捷方式等收尾操作"""
        from EasiAuto.view.oobe.steps import SystemStep

        for step in self.steps:
            if isinstance(step, SystemStep):
                step.create_shortcuts()
        super().accept()

    def done(self, result: int) -> None:
        # 无论完成、跳过还是直接关闭，均视为已完成，下次启动不再出现
        config.Internal.IsOobeCompleted = True
        super().done(result)
