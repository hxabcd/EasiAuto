import atexit
import datetime as dt
import platform
import sys
import traceback
import uuid
import winsound
from pathlib import Path
from typing import Any

import psutil
import sentry_sdk
from loguru import logger

from PySide6.QtCore import QPoint, Qt, QtMsgType, QUrl, qInstallMessageHandler
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QHBoxLayout
from qfluentwidgets import (
    CheckBox,
    Dialog,
    FluentIcon,
    Flyout,
    FlyoutAnimationType,
    ImageLabel,
    InfoBarIcon,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
)

from EasiAuto import __version__
from EasiAuto.common.config import config
from EasiAuto.common.consts import IS_DEV, LOG_DIR
from EasiAuto.common.utils import get_resource, restart, stop

SENTRY_DSN = "https://992aafe788df5155ed58c1498188ae6b@o4510727360348160.ingest.us.sentry.io/4510727362248704"
SENTRY_ATTACH_DEBUG_CONTEXT = True

ERROR_DEBOUNCE = dt.timedelta(seconds=2)
last_error_time = dt.datetime.now() - ERROR_DEBOUNCE
error_dialog_showing = False
ignore_errors: list[str] = []


class StreamToLogger:
    """重定向 print() 到 loguru"""

    def write(self, message: str) -> None:
        msg = message.strip()
        if msg:
            logger.opt(depth=1).info(msg)

    def flush(self) -> None:
        pass


def _build_debug_context(source: str, handled: bool) -> dict[str, Any]:
    process = psutil.Process()
    memory_info = process.memory_info()
    return {
        "source": source,
        "handled": handled,
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "argv": sys.argv,
        "memory_usage_mb": round(memory_info.rss / 1024 / 1024, 2),
        "thread_count": process.num_threads(),
        "is_dev": IS_DEV,
    }


def _last_tb_frame(exc_tb: Any) -> tuple[str, int, str]:
    tb_last = exc_tb
    while tb_last and tb_last.tb_next:
        tb_last = tb_last.tb_next
    if not tb_last:
        return "Unknown", 0, "Unknown"

    frame = tb_last.tb_frame
    return Path(frame.f_code.co_filename).name, tb_last.tb_lineno, frame.f_code.co_name


def _log_exception(
    exc_type: type, exc_value: BaseException, exc_tb: Any, source: str, handled: bool
) -> tuple[str, str]:
    file_name, line_no, func_name = _last_tb_frame(exc_tb)
    process = psutil.Process()
    memory_info = process.memory_info()
    thread_count = process.num_threads()

    prefix = "业务异常" if handled else "未捕获异常"
    log_msg = f"""{prefix}:
├─来源: {source}
├─异常类型: {exc_type.__name__}
├─异常信息: {exc_value}
├─发生位置: {file_name}:{line_no} in {func_name}
├─运行状态: 内存使用 {memory_info.rss / 1024 / 1024:.1f}MB 线程数: {thread_count}
└─详细堆栈信息:"""
    tip_msg = f"""异常类型: {exc_type.__name__}
└─发生位置: {file_name}:{line_no} in {func_name}"""

    logger.opt(exception=(exc_type, exc_value, exc_tb), depth=0).error(log_msg)
    logger.complete()
    return log_msg, tip_msg


def _capture_exception_to_sentry(exc_info: tuple[type, BaseException, Any], source: str, handled: bool) -> str | None:
    if not sentry_sdk.get_client().is_active():
        return None

    if SENTRY_ATTACH_DEBUG_CONTEXT:
        debug_context = _build_debug_context(source, handled)
    else:
        debug_context = {"source": source, "handled": handled}

    with sentry_sdk.push_scope() as scope:
        scope.set_tag("source", source)
        scope.set_tag("handled", str(handled).lower())
        scope.set_context("runtime", debug_context)
        return sentry_sdk.capture_exception(exc_info)


def capture_handled_exception(
    error: BaseException, source: str = "unknown", extra_context: dict[str, Any] | None = None
) -> str | None:
    """统一上报业务已处理异常"""
    exc_type = type(error)
    exc_tb = error.__traceback__
    exc_info = (exc_type, error, exc_tb)

    _log_exception(exc_type, error, exc_tb, source=source, handled=True)
    event_id = _capture_exception_to_sentry(exc_info, source=source, handled=True)

    if sentry_sdk.get_client().is_active() and extra_context:
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("source", source)
            scope.set_tag("handled", "true")
            scope.set_context("extra_context", extra_context)
            sentry_sdk.capture_message("handled_exception_extra_context", level="info")
    return event_id


def qt_message_handler(mode: QtMsgType, context: Any, message: str) -> None:
    """Qt 消息转发到 loguru"""
    msg = message.strip()
    if not msg:
        return
    if mode in (QtMsgType.QtFatalMsg, QtMsgType.QtCriticalMsg):
        logger.critical(msg)
    logger.complete()


class ErrorDialog(Dialog):
    def __init__(self, error_details: str = "Traceback (most recent call last):", parent: Any | None = None) -> None:
        if error_details.endswith(("KeyboardInterrupt", "KeyboardInterrupt\n")):
            stop()

        super().__init__(
            "EasiAuto 崩溃报告",
            "抱歉！EasiAuto 发生了严重的错误从而无法正常运行。您可以保存下方的错误信息并向他人求助。"
            + "若您认为这是程序的Bug，请点击“报告此问题”或联系开发者。",
            parent,
        )

        global error_dialog_showing
        error_dialog_showing = True

        self.is_dragging = False
        self.drag_position = QPoint()
        self.title_bar_height = 30
        self.title_layout = QHBoxLayout()

        self.iconLabel = ImageLabel()
        try:
            self.iconLabel.setImage(get_resource("icons/EasiAuto.ico"))
        except Exception:
            logger.warning("未能加载崩溃报告图标")
        self.error_log = PlainTextEdit()
        self.report_problem = PushButton(FluentIcon.FEEDBACK, "报告此问题")
        self.copy_log_btn = PushButton(FluentIcon.COPY, "复制日志")
        self.ignore_error_btn = PushButton(FluentIcon.INFO, "忽略错误")
        self.ignore_same_error = CheckBox()
        self.ignore_same_error.setText("在下次启动之前，忽略此错误")
        self.restart_btn = PrimaryPushButton(FluentIcon.SYNC, "重新启动")

        self.iconLabel.setScaledContents(True)
        self.iconLabel.setFixedSize(50, 50)
        self.titleLabel.setText("出错啦！ヽ(*。>Д<)o゜")
        self.titleLabel.setStyleSheet("font-family: Microsoft YaHei UI; font-size: 25px; font-weight: bold;")
        self.error_log.setReadOnly(True)
        self.error_log.setPlainText(error_details)
        self.error_log.setMinimumHeight(200)
        self.error_log.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.restart_btn.setFixedWidth(150)
        self.yesButton.hide()
        self.cancelButton.hide()
        self.title_layout.setSpacing(12)
        self.resize(650, 450)
        QApplication.processEvents()

        self.report_problem.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/hxabcd/EasiAuto/issues/"))
        )
        self.copy_log_btn.clicked.connect(self.copy_log)
        self.ignore_error_btn.clicked.connect(self.ignore_error)
        self.restart_btn.clicked.connect(restart)

        self.title_layout.addWidget(self.iconLabel)
        self.title_layout.addWidget(self.titleLabel)
        self.textLayout.insertLayout(0, self.title_layout)
        self.textLayout.addWidget(self.error_log)
        self.textLayout.addWidget(self.ignore_same_error)
        self.buttonLayout.insertStretch(0, 1)
        self.buttonLayout.insertWidget(0, self.copy_log_btn)
        self.buttonLayout.insertWidget(1, self.report_problem)
        self.buttonLayout.insertStretch(1)
        self.buttonLayout.insertWidget(4, self.ignore_error_btn)
        self.buttonLayout.insertWidget(5, self.restart_btn)

    def copy_log(self) -> None:
        QApplication.clipboard().setText(self.error_log.toPlainText())
        Flyout.create(
            icon=InfoBarIcon.SUCCESS,
            title=self.tr("复制成功！ヾ(^▽^*)))"),
            content=self.tr("日志已成功复制到剪贴板。"),
            target=self.copy_log_btn,
            parent=self,
            isClosable=True,
            aniType=FlyoutAnimationType.PULL_UP,
        )

    def ignore_error(self) -> None:
        if self.ignore_same_error.isChecked():
            ignore_errors.append("\n".join(self.error_log.toPlainText().splitlines()[2:]) + "\n")
        self.close()
        global error_dialog_showing
        error_dialog_showing = False

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.y() <= self.title_bar_height:
            self.is_dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: Any) -> None:
        if self.is_dragging:
            self.move(event.globalPos() - self.drag_position)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False


def handle_unhandled_exception(exc_type: type, exc_value: BaseException, exc_tb: Any, source: str) -> None:
    global last_error_time

    error_details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    if error_details in ignore_errors:
        return

    now = dt.datetime.now()
    if now - last_error_time <= ERROR_DEBOUNCE:
        return
    last_error_time = now

    _, tip_msg = _log_exception(exc_type, exc_value, exc_tb, source=source, handled=False)
    _capture_exception_to_sentry((exc_type, exc_value, exc_tb), source=source, handled=False)

    if error_dialog_showing:
        return
    try:
        w = ErrorDialog(f"{tip_msg}\n{error_details}")
        winsound.MessageBeep(winsound.MB_ICONHAND)
        w.exec()
    except Exception as dialog_error:
        logger.critical(f"显示错误对话框失败: {dialog_error}")


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    # 过滤重复信息
    if "log_record" in hint:
        message = event.get("message", "")
        if isinstance(message, str) and "├─" in message:
            return None
    return event


def init_sentry() -> None:
    logger.debug(f"遥测已{'禁用' if not config.App.TelemetryEnabled else '启用'}")
    if not config.App.TelemetryEnabled:
        return

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        before_send=_before_send,  # type: ignore
        release=f"EasiAuto@{__version__}",
        environment="development" if IS_DEV else "production",
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        in_app_include=["EasiAuto"],
        enable_logs=True,
    )

    machine_id = uuid.UUID(int=uuid.getnode()).hex
    sentry_sdk.set_user({"id": machine_id})
    sentry_sdk.set_tag("version", __version__)
    if SENTRY_ATTACH_DEBUG_CONTEXT:
        sentry_sdk.set_context("boot_runtime", _build_debug_context(source="init", handled=True))

    atexit.register(lambda: sentry_sdk.flush(timeout=1.0))


def init_exception_handler() -> None:
    """初始化异常处理与日志"""
    logger.remove()
    log_format = (
        "<green>{time:HH:mm:ss.SSS}</green> | "
        "<level>{level: <7}</level> | "
        "<cyan>{name}</cyan>@<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    logger.add(
        sys.stderr,
        format=log_format,
        colorize=True,
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    logger.debug("初始化异常处理与日志")
    logger.debug(f"日志存储已{'禁用' if not config.App.LogEnabled else '启用'}")
    if config.App.LogEnabled:
        logger.add(
            LOG_DIR / "EasiAuto_{time}.log",
            format=log_format,
            encoding="utf-8",
            enqueue=True,
            backtrace=True,
            diagnose=True,
        )

    # 安装统一异常链路
    sys.stdout = StreamToLogger()
    sys.stderr = StreamToLogger()
    qInstallMessageHandler(qt_message_handler)
    atexit.register(logger.complete)

    init_sentry()
    sys.excepthook = lambda exc_type, exc_value, exc_tb: handle_unhandled_exception(
        exc_type,
        exc_value,
        exc_tb,
        source="python_global",
    )
