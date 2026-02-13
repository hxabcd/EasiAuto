import sys
import time
from argparse import ArgumentParser
from typing import assert_never

import windows11toast
from loguru import logger
from packaging.version import Version

from EasiAuto import __version__, utils
from EasiAuto.config import LoginMethod, UpdateMode, config
from EasiAuto.ui import MainWindow, app

utils.init_exception_handler()
utils.init_exit_signal_handlers()


def login_finished(message: str):
    """登录结束后的回调"""
    # 检查是否失败
    if "失败" in message:
        logger.error(f"自动化登录失败: {message}")
        windows11toast.notify(
            title="自动登录失败",
            body=f"{message}\n请检查日志获取详细信息",
            icon_placement=windows11toast.IconPlacement.APP_LOGO_OVERRIDE,
            icon_hint_crop=windows11toast.IconCrop.NONE,
            icon_src=utils.get_resource("EasiAuto.ico"),
        )
        utils.stop(1)

    # 成功则检查更新
    from EasiAuto.update import update_checker

    if config.Update.CheckAfterLogin and config.Update.Mode.value > UpdateMode.NEVER.value:
        decision = update_checker.check()
        if decision.available and decision.downloads:
            if config.Update.Mode.value >= UpdateMode.CHECK_AND_INSTALL.value:
                file = update_checker.download_update(decision.downloads[0])
                app.aboutToQuit.connect(lambda: update_checker.apply_script(file, reopen=False))
            else:  # 其他情形仅通知
                windows11toast.notify(
                    title="更新可用",
                    body=f"新版本：{decision.target_version}\n打开应用查看详细信息",
                    icon_placement=windows11toast.IconPlacement.APP_LOGO_OVERRIDE,
                    icon_hint_crop=windows11toast.IconCrop.NONE,
                    icon_src=utils.get_resource("EasiAuto.ico"),
                )

    utils.stop()


def cmd_login(args):
    """login 子命令 - 执行自动登录"""

    # 若临时禁用，则退出程序
    if config.Login.SkipOnce:
        logger.info("已通过配置文件禁用，正在退出")
        config.Login.SkipOnce = False

        utils.stop()

    logger.debug(f"传入的参数：\n{'\n'.join([f' - {key}: {value}' for key, value in vars(args).items()])}")

    from EasiAuto.automator import CVAutomator, FixedAutomator, UIAAutomator
    from EasiAuto.components import DialogResponse, PreRunPopup, WarningBanner

    # 显示警告弹窗
    if config.Warning.Enabled and not args.manual:
        try:
            msgbox = PreRunPopup()
            delays = 0
            while True:
                if delays >= config.Warning.MaxDelays:
                    msgbox.delay_btn.hide()
                response = msgbox.countdown(config.Warning.Timeout)
                match response:
                    case DialogResponse.CANCEL:
                        logger.info("用户取消操作，正在退出")
                        utils.stop()
                        sys.exit(0)
                    case DialogResponse.CONTINUE:
                        logger.info("用户确认继续，继续执行")
                        break
                    case DialogResponse.TIMEOUT:
                        logger.info("等待超时，继续执行")
                        break
                    case DialogResponse.DELAY:
                        logger.info(f"用户选择推迟，等待 {config.Warning.DelayTime} 秒...")
                        delays += 1
                        time.sleep(config.Warning.DelayTime)
                        continue
                    case unreachable:
                        assert_never(unreachable)
        except Exception:
            logger.error("显示警告弹窗时出错，跳过警告")

    # NOTE: 下方运行逻辑在 ui.py _handle_action_run() 中存在相同实现，如更改需同步替换

    # 显示警示横幅
    if config.Banner.Enabled:
        try:
            screen = app.primaryScreen().geometry()
            banner = WarningBanner(config.Banner.Style)
            banner.setGeometry(0, 80, screen.width(), 140)  # 顶部横幅
            banner.show()
        except Exception:
            logger.error("显示横幅时出错，跳过横幅")

    # 执行登录
    logger.debug(f"当前设置的登录方案: {config.Login.Method}")
    match config.Login.Method:  # 选择登录方案
        case LoginMethod.UIA:
            automator_type = UIAAutomator
        case LoginMethod.OPENCV:
            automator_type = CVAutomator
        case LoginMethod.FIXED:
            automator_type = FixedAutomator
        case unreachable:
            assert_never(unreachable)

    automator = automator_type(args.account, args.password)

    automator.start()
    automator.finished.connect(login_finished)
    sys.exit(app.exec())


def cmd_settings(_):
    """settings 子命令 - 打开设置界面"""

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


def cmd_skip(_):
    """skip 子命令 - 跳过下一次登录"""
    config.Login.SkipOnce = True
    logger.success("已更新配置文件，正在退出")
    utils.stop()


def main():
    # 单例检查
    if not utils.check_singleton():
        utils.stop()

    # 解析命令行参数
    parser = ArgumentParser(prog="EasiAuto", description="一款自动登录希沃白板的小工具")
    subparsers = parser.add_subparsers(title="子命令", dest="command")

    # login 子命令
    login_parser = subparsers.add_parser("login", help="登录账号")
    login_parser.add_argument("-a", "--account", required=True, help="账号")
    login_parser.add_argument("-p", "--password", required=True, help="密码")
    login_parser.add_argument("-m", "--manual", action="store_true", help="手动执行（不显示确认弹窗）")
    login_parser.set_defaults(func=cmd_login)

    # settings 子命令
    setting_parser = subparsers.add_parser("settings", help="打开设置界面")
    setting_parser.set_defaults(func=cmd_settings)

    # skip 子命令
    skip_parser = subparsers.add_parser("skip", help="跳过下一次登录")
    skip_parser.set_defaults(func=cmd_skip)

    args = parser.parse_args()

    if hasattr(args, "func"):
        if args.func != cmd_skip:
            if config.Update.LastVersion != "Unknown":
                try:
                    last_version = Version(config.Update.LastVersion)
                except Exception as e:
                    logger.warning(f"解析上个版本时发生异常：{e}")
                else:
                    if last_version < Version(__version__):
                        windows11toast.notify(
                            title=f"已更新至 {__version__}",
                            body=f"{config.Update.LastVersion} -> {__version__}",
                            icon_placement=windows11toast.IconPlacement.APP_LOGO_OVERRIDE,
                            icon_hint_crop=windows11toast.IconCrop.NONE,
                            icon_src=utils.get_resource("EasiAuto.ico"),
                        )
            config.Update.LastVersion = __version__
        args.func(args)
    else:
        cmd_settings(args)


if __name__ == "__main__":
    main()
