import logging
import multiprocessing
import sys
from argparse import ArgumentParser

from PySide6.QtWidgets import QApplication
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_fixed

from automator import BaseAutomator, CVAutomator, FixedAutomator, UIAAutomator
from ui import WarningBanner, WarningPopupWindow
from utils import init

config = init()


# -------- 自动登录相关 --------


# 显示警告弹窗
def show_warning():
    app = QApplication.instance() or QApplication([])  # noqa: F841
    msgbox = WarningPopupWindow()

    if msgbox.countdown(config.warning.timeout) == 0:
        logging.info("用户取消操作，正在退出")
        sys.exit(0)
    logging.info("用户确认或超时，继续执行")

    app.quit()


# 显示警告横幅
def show_banner():
    app = QApplication.instance() or QApplication([])
    screen = app.primaryScreen().geometry()
    w = WarningBanner(config.banner)
    w.setGeometry(0, 80, screen.width(), 140)  # 顶部横幅
    w.show()
    app.exec()


# 带重试的登录
@retry(
    stop=stop_after_attempt(config.app.max_retries + 1),
    wait=wait_fixed(2),
    before_sleep=before_sleep_log(logging.getLogger(), logging.ERROR),
)
def run_login(automator: BaseAutomator):
    automator.run()


# -------- 命令解析 --------


def cmd_login(args):
    """login 子命令 - 执行自动登录"""

    # 若临时禁用，则退出程序
    if config.login.skip_once:
        logging.info("已通过配置文件禁用，正在退出")
        config.login.skip_once = False
        sys.exit(0)

    logging.debug("传入的参数：\n%s" % "\n".join([f" - {key}: {value}" for key, value in vars(args).items()]))

    # 显示警告
    if config.warning.enabled:
        try:
            show_warning()
        except Exception:
            logging.exception("显示警告通知时出错，跳过警告")

    # 显示横幅
    if config.banner.enabled:
        try:
            p = multiprocessing.Process(target=show_banner, daemon=True)
            p.start()
        except Exception:
            logging.exception("显示横幅时出错，跳过横幅")

    # 执行登录
    logging.debug(f"当前设置的登录方案: {config.login.method}")
    match config.login.method:  # 选择登录方案
        case "UIAutomation":
            automator = UIAAutomator(args.account, args.password, config.login)
        case "OpenCV":
            automator = CVAutomator(args.account, args.password, config.login)
        case "FixedPosition":
            automator = FixedAutomator(args.account, args.password, config.login)
        case _:
            logging.warning("未知方案，已回滚至默认值 (UI Automation)")
            automator = UIAAutomator(args.account, args.password, config.login)

    run_login(automator)

    logging.info("执行完毕")
    sys.exit(0)


def cmd_settings(args):
    """settings 子命令 - 打开设置界面"""
    ...  # 0.4 未实装内容


def cmd_skip(args):
    """skip 子命令 - 跳过下一次登录"""
    config.login.skip_once = True
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

    # # settings 子命令
    # setting_parser = subparsers.add_parser("settings", help="打开设置界面")
    # setting_parser.set_defaults(func=cmd_settings)

    # skip 子命令
    skip_parser = subparsers.add_parser("skip", help="跳过下一次登录")
    skip_parser.set_defaults(func=cmd_skip)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
