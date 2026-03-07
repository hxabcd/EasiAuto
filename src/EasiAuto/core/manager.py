from PySide6.QtCore import QObject, QThread, Signal

from EasiAuto.common.config import LoginMethod, config

from . import BaseAutomator, CVAutomator, FixedAutomator, InjectAutomator, UIAAutomator


class AutomationManager(QObject):
    task_update = Signal(str)
    progress_update = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, account: str, password: str):
        super().__init__()
        self._worker_thread: QThread | None = None
        self._executor: BaseAutomator | None = None
        self._account = account
        self._password = password

    def _get_strategy_class(self) -> type[BaseAutomator]:
        strategies: dict[LoginMethod, type[BaseAutomator]] = {
            LoginMethod.FIXED: FixedAutomator,
            LoginMethod.CV: CVAutomator,
            LoginMethod.UIA: UIAAutomator,
            LoginMethod.INJECT: InjectAutomator,
        }
        return strategies.get(config.Login.Method, FixedAutomator)

    def run(self):
        if self._worker_thread and self._worker_thread.isRunning():
            return

        strategy_class = self._get_strategy_class()
        self._executor = strategy_class(account=self._account, password=self._password)
        self._worker_thread = QThread()

        self._executor.moveToThread(self._worker_thread)

        self._executor.task_update.connect(self.task_update)
        self._executor.progress_update.connect(self.progress_update)
        self._executor.finished.connect(self._handle_finished)

        self._worker_thread.started.connect(self._executor.run)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        self._worker_thread.start()

    def _run_sync(self):
        strategy_class = self._get_strategy_class()
        self._executor = strategy_class(account=self._account, password=self._password)

        self._executor.task_update.connect(self.task_update)
        self._executor.progress_update.connect(self.progress_update)
        self._executor.finished.connect(self._handle_finished)

        self._executor.run()

    def _handle_finished(self, success: bool, message: str):
        """处理结束逻辑并关闭线程"""
        self.finished.emit(success, message)

        if self._worker_thread:
            self._worker_thread.quit()

    def stop(self):
        """停止当前任务"""
        if self._worker_thread and self._worker_thread.isRunning():
            self._worker_thread.quit()
            self._worker_thread.wait()
