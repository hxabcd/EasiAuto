from loguru import logger

from PySide6.QtCore import QObject, Signal

from EasiAuto.common.config import LoginMethod, config

from . import BaseAutomator, CVAutomator, FixedAutomator, InjectAutomator, UIAAutomator


class AutomationManager(QObject):
    started = Signal()
    finished = Signal()
    failed = Signal(str)
    task_update = Signal(str)
    progress_update = Signal(str)

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

    def run(self, account: str, password: str):
        if self._automator and self._automator.isRunning():
            logger.warning("已有一个正在运行的登录任务")
            return

        strategy_class = self._get_strategy_class(config.Login.Method)
        self._automator = strategy_class(account, password)

        self._automator.started.connect(self.started)
        self._automator.finished.connect(self.finished)
        self._automator.failed.connect(self.failed)
        self._automator.task_update.connect(self.task_update)
        self._automator.progress_update.connect(self.progress_update)

        self._automator.start()

    def stop(self):
        """停止当前任务"""
        if self._automator and self._automator.isRunning():
            logger.info("正在停止当前任务")
            self._automator.requestInterruption()


automation_manager = AutomationManager()
