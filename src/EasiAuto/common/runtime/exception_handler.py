import atexit
import datetime as dt
import sys
import traceback
import winsound
from pathlib import Path
from typing import Any

import psutil
import sentry_sdk
from loguru import logger
from sentry_sdk.integrations.loguru import LoguruIntegration

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

error_cooldown = dt.timedelta(seconds=2)  # 冷却时间(s)
ignore_errors = []
last_error_time = dt.datetime.now() - error_cooldown  # 上一次错误
error_dialog = None

class StreamToLogger:
    """重定向 print() 到 loguru"""

    def write(self, message):
        msg = message.strip()
        if msg:
            logger.opt(depth=1).info(msg)

    def flush(self):
        pass


def qt_message_handler(mode: QtMsgType, context, message):  # noqa
    """Qt 消息转发到 loguru"""
    msg = message.strip()
    if not msg:
        return
    match mode:
        case QtMsgType.QtFatalMsg:
            logger.critical(msg)
        case QtMsgType.QtCriticalMsg:
            logger.error(msg)
    if IS_DEV:
        match mode:
            case QtMsgType.QtWarningMsg:
                logger.warning(msg)
            case QtMsgType.QtInfoMsg | QtMsgType.QtSystemMsg:
                logger.info(msg)
            case QtMsgType.QtDebugMsg:
                logger.debug(msg)
    logger.complete()


class ErrorDialog(Dialog):  # 重大错误提示框
    def __init__(
        self,
        error_details: str = "Traceback (most recent call last):",
        parent: Any | None = None,
    ) -> None:
        # KeyboardInterrupt 直接 exit
        if error_details.endswith(("KeyboardInterrupt", "KeyboardInterrupt\n")):
            stop()

        global error_dialog

        super().__init__(
            "EasiAuto 崩溃报告",
            "抱歉！EasiAuto 发生了严重的错误从而无法正常运行。您可以保存下方的错误信息并向他人求助。"
            + "若您认为这是程序的Bug，请点击“报告此问题”或联系开发者。",
            parent,
        )

        error_dialog = True

        self.is_dragging = False
        self.drag_position = QPoint()
        self.title_bar_height = 30

        self.title_layout = QHBoxLayout()

        self.iconLabel = ImageLabel()
        try:
            self.iconLabel.setImage(get_resource("EasiAuto.ico"))
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
        self.error_log.setReadOnly(True)  # 只读模式
        self.error_log.setPlainText(error_details)
        self.error_log.setMinimumHeight(200)
        self.error_log.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard  # 允许鼠标和键盘选择文本
        )
        self.restart_btn.setFixedWidth(150)
        self.yesButton.hide()
        self.cancelButton.hide()  # 隐藏取消按钮
        self.title_layout.setSpacing(12)
        self.resize(650, 450)
        QApplication.processEvents()

        # 按钮事件
        self.report_problem.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/hxabcd/EasiAuto/issues/"))
        )
        self.copy_log_btn.clicked.connect(self.copy_log)
        self.ignore_error_btn.clicked.connect(self.ignore_error)
        self.restart_btn.clicked.connect(restart)

        self.title_layout.addWidget(self.iconLabel)  # 标题布局
        self.title_layout.addWidget(self.titleLabel)
        self.textLayout.insertLayout(0, self.title_layout)  # 页面
        self.textLayout.addWidget(self.error_log)
        self.textLayout.addWidget(self.ignore_same_error)
        self.buttonLayout.insertStretch(0, 1)  # 按钮布局
        self.buttonLayout.insertWidget(0, self.copy_log_btn)
        self.buttonLayout.insertWidget(1, self.report_problem)
        self.buttonLayout.insertStretch(1)
        self.buttonLayout.insertWidget(4, self.ignore_error_btn)
        self.buttonLayout.insertWidget(5, self.restart_btn)

    def copy_log(self) -> None:  # 复制日志
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
        global error_dialog
        error_dialog = False

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.LeftButton and event.y() <= self.title_bar_height:
            self.is_dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: Any) -> None:
        if self.is_dragging:
            self.move(event.globalPos() - self.drag_position)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.LeftButton:
            self.is_dragging = False


@logger.catch
def log_exception(exc_type: type, exc_value: Exception, exc_tb: Any, prefix: str = "发生全局异常") -> tuple[str, str]:
    """记录详细异常信息到日志"""
    # 获取异常抛出位置
    tb_last = exc_tb
    while tb_last and tb_last.tb_next:  # 找到最后一帧
        tb_last = tb_last.tb_next

    if tb_last:
        frame = tb_last.tb_frame
        file_name = Path(frame.f_code.co_filename).name
        line_no = tb_last.tb_lineno
        func_name = frame.f_code.co_name
    else:
        file_name, line_no, func_name = "Unknown", 0, "Unknown"

    process = psutil.Process()
    memory_info = process.memory_info()
    thread_count = process.num_threads()

    log_msg = f"""{prefix}:
├─异常类型: {exc_type.__name__} {exc_type}
├─异常信息: {exc_value}
├─发生位置: {file_name}:{line_no} in {func_name}
├─运行状态: 内存使用 {memory_info.rss / 1024 / 1024:.1f}MB 线程数: {thread_count}
└─详细堆栈信息:"""
    tip_msg = f"""异常类型: {exc_type.__name__} {exc_type}
└─发生位置: {file_name}:{line_no} in {func_name}"""

    logger.opt(exception=(exc_type, exc_value, exc_tb), depth=0).error(log_msg)
    logger.complete()

    # 发送至 Sentry
    if sentry_sdk.get_client().is_active():
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("prefix", prefix)
            scope.set_context(
                "runtime_status",
                {
                    "memory_usage_mb": f"{memory_info.rss / 1024 / 1024:.1f}",
                    "thread_count": thread_count,
                },
            )
            sentry_sdk.capture_exception((exc_type, exc_value, exc_tb))

    return log_msg, tip_msg


@logger.catch
def global_exceptHook(exc_type: type, exc_value: Exception, exc_tb: Any) -> None:
    error_details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    if error_details in ignore_errors:
        return
    global last_error_time
    current_time = dt.datetime.now()
    if current_time - last_error_time > error_cooldown:
        last_error_time = current_time

        log_msg, tip_msg = log_exception(exc_type, exc_value, exc_tb)

        if not error_dialog:
            try:
                w = ErrorDialog(f"{tip_msg}\n{error_details}")
                winsound.MessageBeep(winsound.MB_ICONHAND)
                w.exec()
            except Exception as e:
                logger.critical(f"显示错误对话框失败: {e}")


def init_exception_handler():
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
            rotation="1 MB",
            retention="1 minute",
            encoding="utf-8",
            enqueue=True,
            backtrace=True,
            diagnose=True,
        )
    sys.stdout = StreamToLogger()
    sys.stderr = StreamToLogger()
    qInstallMessageHandler(qt_message_handler)
    atexit.register(logger.complete)

    # 初始化 Sentry
    logger.debug(f"遥测已{'禁用' if not config.App.TelemetryEnabled else '启用'}")
    if config.App.TelemetryEnabled:

        def before_send(event, hint):
            """过滤重复上报日志"""
            if "log_record" in hint:
                message = event.get("message", "")
                if message and "├─" in message:
                    return None
            return event

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[LoguruIntegration(event_level=50)],  # CRITICAL
            before_send=before_send,
            release=f"EasiAuto@{__version__}",
            environment="development" if IS_DEV else "production",
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )

    sys.excepthook = global_exceptHook
