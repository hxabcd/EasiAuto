import logging
import multiprocessing
import sys
from argparse import ArgumentParser

from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentTranslator,
    Theme,
    setTheme,
)
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_fixed

from automator import BaseAutomator, CVAutomator, FixedAutomator, UIAAutomator
from components import WarningBanner, WarningPopupWindow
from ui import MainSettingsWindow
from utils import init, toggle_skip

config = init()


# -------- 自动登录相关 --------


# 显示警告弹窗
def show_warning():
    app = QApplication.instance() or QApplication([])  # noqa: F841
    msgbox = WarningPopupWindow()

    if msgbox.countdown(config.Warning.Timeout) == 0:
        logging.info("用户取消操作，正在退出")
        sys.exit(0)
    logging.info("用户确认或超时，继续执行")

    app.quit()


# 显示警告横幅
def show_banner():
    app = QApplication.instance() or QApplication([])
    screen = app.primaryScreen().geometry()
    w = WarningBanner(config.Banner)
    w.setGeometry(0, 80, screen.width(), 140)  # 顶部横幅
    w.show()

    app.exec()


# 带重试的登录
@retry(
    stop=stop_after_attempt(config.App.MaxRetries + 1),
    wait=wait_fixed(2),
    before_sleep=before_sleep_log(logging.getLogger(), logging.ERROR),
)
def run_login(automator: BaseAutomator):
    automator.run()


# -------- 命令解析 --------


def cmd_login(args):
    """login 子命令 - 执行自动登录"""

    # 若临时禁用，则退出程序
    if config.Login.SkipOnce:
        logging.info("已通过配置文件禁用，正在退出")
        toggle_skip(config, False)

        sys.exit(0)

    logging.debug("传入的参数：\n%s" % "\n".join([f" - {key}: {value}" for key, value in vars(args).items()]))

    # 显示警告
    if config.Warning.Enabled:
        try:
            show_warning()
        except Exception:
            logging.exception("显示警告通知时出错，跳过警告")

    # 显示横幅
    if config.Banner.Enabled:
        try:
            p = multiprocessing.Process(target=show_banner, daemon=True)
            p.start()
        except Exception:
            logging.exception("显示横幅时出错，跳过横幅")

    # 执行登录
    logging.debug(f"当前设置的登录方案: {config.Login.Method}")
    match config.Login.Method:  # 选择登录方案
        case "UIAutomation":
            automator = UIAAutomator(args.account, args.password, config.Login, config.EasiNote, config.Timeout)
        case "OpenCV":
            automator = CVAutomator(args.account, args.password, config.Login, config.EasiNote, config.Timeout)
        case "FixedPosition":
            automator = FixedAutomator(args.account, args.password, config.Login, config.EasiNote, config.Timeout)
        case _:
            logging.warning("未知方案，已回滚至默认值 (UI Automation)")
            automator = UIAAutomator(args.account, args.password, config.Login, config.EasiNote, config.Timeout)

    run_login(automator)

    logging.info("执行完毕")
    sys.exit(0)


def cmd_settings(args):
    """settings 子命令 - 打开设置界面"""
    app = QApplication(sys.argv)

    translator = FluentTranslator()
    app.installTranslator(translator)
    setTheme(Theme.AUTO)

    window = MainSettingsWindow()
    window.show()
    sys.exit(app.exec())


def cmd_skip(args):
    """skip 子命令 - 跳过下一次登录"""
    toggle_skip(config, True)
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
