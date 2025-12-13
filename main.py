import logging
import sys
from argparse import ArgumentParser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentTranslator,
    Theme,
    setTheme,
    setThemeColor,
)

from automator import CVAutomator, FixedAutomator, UIAAutomator
from components import WarningBanner, WarningPopupWindow
from config import Config
from ui import MainSettingsWindow


def set_logger(level=logging.WARNING):
    try:  # 使用彩色日志
        import coloredlogs

        coloredlogs.install(
            level=level,
            fmt="[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    except Exception:  # 回退基本日志
        logging.basicConfig(
            level=level,
            format="[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
            force=True,
        )


set_logger(logging.DEBUG)  # 预初始化
config = Config.load()

# -------- 命令解析 --------


def cmd_login(args):
    """login 子命令 - 执行自动登录"""

    # 启用DPI缩放并创建 QApplication
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([])

    # 若临时禁用，则退出程序
    if config.Login.SkipOnce:
        logging.info("已通过配置文件禁用，正在退出")
        config.Login.SkipOnce = False

        sys.exit(0)

    logging.debug("传入的参数：\n%s" % "\n".join([f" - {key}: {value}" for key, value in vars(args).items()]))

    # 显示警告弹窗
    if config.Warning.Enabled:
        try:
            msgbox = WarningPopupWindow()
            if msgbox.countdown(config.Warning.Timeout) == 0:
                logging.info("用户取消操作，正在退出")
                sys.exit(0)
            logging.info("用户确认或超时，继续执行")
        except Exception:
            logging.exception("显示警告通知时出错，跳过警告")

    # 显示警示横幅
    if config.Banner.Enabled:
        try:
            screen = app.primaryScreen().geometry()
            banner = WarningBanner(config.Banner)
            banner.setGeometry(0, 80, screen.width(), 140)  # 顶部横幅
            banner.show()
        except Exception:
            logging.exception("显示横幅时出错，跳过横幅")

    # 执行登录
    logging.debug(f"当前设置的登录方案: {config.Login.Method}")
    match config.Login.Method:  # 选择登录方案
        case "UIAutomation":
            automatorType = UIAAutomator
        case "OpenCV":
            automatorType = CVAutomator
        case "FixedPosition":
            automatorType = FixedAutomator
        case unknown:
            logging.warning(f"未知方案 {unknown}，已回滚至默认值 (UI Automation)")
            automatorType = UIAAutomator

    automator = automatorType(args.account, args.password, config.Login, config.App.MaxRetries)

    automator.start()
    automator.finished.connect(app.quit)

    sys.exit(app.exec())


def cmd_settings(args):
    """settings 子命令 - 打开设置界面"""
    app = QApplication(sys.argv)

    translator = FluentTranslator()
    app.installTranslator(translator)
    setTheme(Theme.AUTO)
    setThemeColor("#00C884")

    window = MainSettingsWindow()
    window.show()
    sys.exit(app.exec())


def cmd_skip(args):
    """skip 子命令 - 跳过下一次登录"""
    config.Login.SkipOnce = True
    logging.info("已更新配置文件，正在退出")
    sys.exit(0)


def main():
    # 解析命令行参数
    parser = ArgumentParser(prog="EasiAuto", description="自动登录希沃白板的CLI工具")
    subparsers = parser.add_subparsers(title="子命令", dest="command")

    # login 子命令
    login_parser = subparsers.add_parser("login", help="登录账号")
    login_parser.add_argument("-a", "--account", required=True, help="账号")
    login_parser.add_argument("-p", "--password", required=True, help="密码")
    login_parser.set_defaults(func=cmd_login)

    # settings 子命令
    setting_parser = subparsers.add_parser("settings", help="打开设置界面")
    setting_parser.set_defaults(func=cmd_settings)

    # skip 子命令
    skip_parser = subparsers.add_parser("skip", help="跳过下一次登录")
    skip_parser.set_defaults(func=cmd_skip)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_settings(args)


if __name__ == "__main__":
    main()
