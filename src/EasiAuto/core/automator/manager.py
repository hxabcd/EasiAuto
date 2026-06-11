from typing import Any

from loguru import logger

from PySide6.QtCore import QObject, Signal

from EasiAuto.core.automator import BaseAutomator, CVAutomator, FixedAutomator, InjectAutomator, UIAAutomator
from EasiAuto.models.config import LoginMethod, config


class AutomationManager(QObject):
    started = Signal()
    finished = Signal()
    successed = Signal()
    interrupted = Signal()
    failed = Signal(str)
    task_updated = Signal(str)
    progress_updated = Signal(str)

    def __init__(self):
        super().__init__()
        self._automator: BaseAutomator | None = None

    def _get_strategy_class(self, strategy: LoginMethod) -> type[BaseAutomator]:
        strategies: dict[LoginMethod, type[BaseAutomator]] = {
            LoginMethod.FIXED: FixedAutomator,
            LoginMethod.CV: CVAutomator,
            LoginMethod.UIA: UIAAutomator,
            LoginMethod.INJECT: InjectAutomator,
        }
        return strategies.get(strategy, FixedAutomator)

    def run(self, type: str, credentials: Any):
        if self._automator and self._automator.isRunning():
            logger.warning("已有一个正在运行的登录任务")
            return

        if type == "qrcode":
            from EasiAuto.core.automator.qrcode import QRCodeAutomator

            logger.info("检测到二维码档案")
            self._automator = QRCodeAutomator(credentials)
        else:
            strategy_class = self._get_strategy_class(config.Login.Method)
            self._automator = strategy_class(*credentials)

        self._automator.started.connect(self.started)
        self._automator.finished.connect(self.finished)
        self._automator.successed.connect(self.successed)
        self._automator.interrupted.connect(self.interrupted)
        self._automator.failed.connect(self.failed)
        self._automator.task_updated.connect(self.task_updated)
        self._automator.progress_updated.connect(self.progress_updated)

        self._automator.start()

    def stop(self):
        """停止当前任务"""
        if self._automator and self._automator.isRunning():
            logger.info("正在停止当前任务")
            self._automator.requestInterruption()


automation_manager = AutomationManager()
