import atexit
import datetime as dt
import os
import signal
import sys
import traceback
import winsound
from pathlib import Path
from typing import Any, NoReturn

import psutil
import sentry_sdk
import win32api
import win32com.client
import win32con
import win32event
import win32gui
import winerror
from loguru import logger
from PySide6.QtCore import QPoint, Qt, QtMsgType, QUrl, qInstallMessageHandler
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget
from qfluentwidgets import (
    CheckBox,
    Dialog,
    FluentIcon,
    Flyout,
    FlyoutAnimationType,
    ImageLabel,
    InfoBar,
    InfoBarIcon,
    InfoBarPosition,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
)
from sentry_sdk.integrations.loguru import LoguruIntegration

from config import config
from consts import EA_EXECUTABLE, SENTRY_DSN, VERSION

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


def qt_message_handler(mode, context, message):  # noqa
    """Qt 消息转发到 loguru"""
    msg = message.strip()
    if not msg:
        return
    if mode == QtMsgType.QtCriticalMsg:
        logger.error(msg)
        logger.complete()
    elif mode == QtMsgType.QtFatalMsg:
        logger.critical(msg)
        logger.complete()
    else:
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
    # 增加安全模式判断？
    error_details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    if error_details in ignore_errors:
        return
    global last_error_time, error_dialog
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
    logger.debug("初始化异常处理与日志")
    logger.debug(f"日志存储已{'禁用' if not config.App.LogEnabled else '启用'}")
    if config.App.LogEnabled:
        logger.add(
            EA_EXECUTABLE.parent / "logs" / "EasiAuto_{time}.log",
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
            integrations=[LoguruIntegration(event_level=None)],
            before_send=before_send,
            release=f"EasiAuto@{VERSION}",
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )

    sys.excepthook = global_exceptHook


_singleton_mutex = None


def check_singleton() -> bool:
    """检查程序是否已在运行"""

    # 互斥锁检查
    global _singleton_mutex
    mutex_name = "EasiAuto_Singleton_Mutex"
    try:
        _singleton_mutex = win32event.CreateMutex(None, False, mutex_name)
        if win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS:
            return True
    except Exception as e:
        logger.error(f"创建互斥锁失败: {e}")

    logger.warning("检测到另一个正在运行的实例 (Mutex)")

    # 尝试查找并切换到已有窗口
    hwnds = get_window_by_title("EasiAuto")
    if hwnds:
        current_pid = os.getpid()
        for hwnd in hwnds:
            try:
                _, pid = win32gui.GetWindowThreadProcessId(hwnd)
                if pid == current_pid:
                    continue
                # 简单验证一下进程名，避免误触 IDE
                proc = psutil.Process(pid)
                proc_name = proc.name().lower()
                if "python" in proc_name or "EasiAuto" in proc_name:
                    switch_window(hwnd)
                    break
            except Exception:
                continue

    # msg_box = QMessageBox()
    # msg_box.setIcon(QMessageBox.Warning)
    # msg_box.setWindowTitle("EasiAuto 已在运行")
    # msg_box.setText("检测到 EasiAuto 已经在运行中。运行多个实例可能会导致功能冲突或配置文件损坏。")
    # msg_box.setInformativeText("您确定要启动另一个实例吗？")
    # msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    # msg_box.setDefaultButton(QMessageBox.No)
    # msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)

    # if msg_box.exec() == QMessageBox.No:
    #     logger.info("用户选择退出程序")
    #     return False

    # logger.info("用户选择继续启动")
    # return True


def get_resource(file: str):
    """获取资源路径"""
    return str(EA_EXECUTABLE.parent / "resources" / file)


def create_shortcut(args: str, name: str, show_result_to: QWidget | None = None):
    """创建 EasiAuto 桌面快捷方式"""
    try:
        name = name + ".lnk"

        logger.info(f"在桌面创建快捷方式: {name}")

        shell = win32com.client.Dispatch("WScript.Shell")
        desktop_path = Path(shell.SpecialFolders("Desktop"))
        shortcut_path = desktop_path / name

        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = str(EA_EXECUTABLE)
        shortcut.Arguments = args
        shortcut.WorkingDirectory = str(EA_EXECUTABLE.parent)
        shortcut.IconLocation = get_resource("EasiAutoShortcut.ico")
        shortcut.Save()

        logger.success("创建成功")
        if show_result_to:
            InfoBar.success(
                title="成功",
                content=f"已在桌面创建 {name}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=show_result_to,
            )
    except Exception as e:
        logger.error(f"创建快捷方式失败: {e}")
        if show_result_to:
            InfoBar.error(
                title="创建失败",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=show_result_to,
            )


def switch_window(hwnd: int):
    """通过句柄切换焦点"""
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)  # 确保窗口不是最小化状态
    win32gui.SetForegroundWindow(hwnd)  # 设置为前台窗口（获取焦点）


def get_window_by_title(title: str):
    """通过标题获取窗口"""

    def callback(hwnd, extra):
        if title in win32gui.GetWindowText(hwnd):
            extra.append(hwnd)

    hwnds = []
    # 枚举所有顶层窗口
    win32gui.EnumWindows(callback, hwnds)

    if hwnds:
        logger.success(f"已找到标题包含 '{title}' 的窗口")
        return hwnds
    logger.warning(f"未找到标题包含 '{title}' 的窗口")
    return None


def get_window_by_pid(pid: int, target_title: str, strict: bool = True) -> int | None:
    """根据进程 PID 查找窗口句柄，支持部分标题匹配。"""
    hwnd_found = None

    def callback(hwnd, _):
        nonlocal hwnd_found
        _, window_pid = win32gui.GetWindowThreadProcessId(hwnd)
        if window_pid == pid:
            window_title = win32gui.GetWindowText(hwnd)
            if (target_title == window_title) if strict else (target_title in window_title):
                hwnd_found = hwnd
                return False  # 找到就停止枚举
        return True

    win32gui.EnumWindows(callback, None)
    return hwnd_found


def get_ci_executable() -> Path | None:
    """获取 ClassIsland 可执行文件位置"""
    try:
        lnk_path = Path(
            os.path.expandvars(
                r"%USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ClassIsland.lnk"
            )
        ).resolve()

        if not lnk_path.exists():
            return None

        # 解析快捷方式
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(lnk_path))
        target = shortcut.TargetPath

        return Path(target).resolve()

    except Exception as e:
        logger.error(f"获取 ClassIsland 路径时出错: {e}")
        return None


def init_exit_signal_handlers() -> None:
    """退出信号处理器"""

    def signal_handler(signum, _):
        logger.debug(f"收到信号 {signal.Signals(signum).name}，退出...")
        stop(0)

    signal.signal(signal.SIGTERM, signal_handler)  # taskkill
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C


def _reset_signal_handlers() -> None:
    """重置信号处理器为默认状态"""
    try:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass


def restart() -> None:
    """重启程序"""
    logger.debug("重启程序")

    app = QApplication.instance()
    if app:
        _reset_signal_handlers()
        app.quit()
        app.processEvents()

    os.execl(sys.executable, sys.executable, *sys.argv)


def clean_up(status):
    app = QApplication.instance()
    logger.debug(f"程序退出({status})")
    if not app:
        os._exit(status)


def stop(status: int = 0) -> None:
    """退出程序"""
    logger.debug("退出程序...")
    app = QApplication.instance()
    if app:
        app.quit()
        app.processEvents()
    clean_up(status)


def crash() -> NoReturn:
    """崩溃程序"""
    raise Exception("Crash Test")
