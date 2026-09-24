"""命令行接口：参数解析、凭据解析与子命令分发

子命令的实现依赖启动器提供的窗口与登录流程入口，故以参数形式接收 Launcher。
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from loguru import logger

from EasiAuto.integrations.easinote.patcher import (
    PATCH_ERR_EASINOTE_NOT_FOUND,
    PATCH_ERR_OPERATION_FAILED,
    PATCH_ERR_UNKNOWN,
    PATCH_OK,
    patch_easinote,
    unpatch_easinote,
)
from EasiAuto.integrations.easinote.path import resolve_easinote_path
from EasiAuto.models.config import config
from EasiAuto.models.profile import EasiAutomation, profile
from EasiAuto.runtime.lifecycle import stop
from EasiAuto.view.helpers import get_app

if TYPE_CHECKING:
    from EasiAuto.launcher import Launcher

# 需要 GUI 的子命令；FORWARDABLE_COMMANDS 为允许由次实例转发给主实例的命令
UI_COMMANDS = {None, "settings", "login", "oobe"}
FORWARDABLE_COMMANDS = {None, "settings", "login", "skip", "oobe"}


@lru_cache(maxsize=1)
def build_parser() -> ArgumentParser:
    """构建命令行解析器（同一进程内复用同一实例）"""
    parser = ArgumentParser(prog="EasiAuto", description="一款自动登录希沃白板的小工具")
    subparsers = parser.add_subparsers(title="子命令", dest="command")

    login_parser = subparsers.add_parser("login", help="登录账号")
    login_target_group = login_parser.add_mutually_exclusive_group(required=True)
    login_target_group.add_argument("-i", "--id", help="档案 ID")
    login_target_group.add_argument("-a", "--account", help="账号")
    login_parser.add_argument("-p", "--password", help="密码（当使用 --account 时必填）")
    login_parser.add_argument("-m", "--manual", action="store_true", help="手动执行（不显示确认弹窗）")

    subparsers.add_parser("settings", help="打开设置界面")
    subparsers.add_parser("oobe", help="重新运行首次设置向导（调试用）")
    subparsers.add_parser("skip", help="跳过下一次登录")

    # 内部子命令，不面向用户
    patch_parser = subparsers.add_parser("patch", help="修补/撤销修补希沃白板（内部命令）")
    patch_group = patch_parser.add_mutually_exclusive_group(required=True)
    patch_group.add_argument("--on", action="store_true", help="执行修补")
    patch_group.add_argument("--off", action="store_true", help="撤销修补")

    return parser


def resolve_credentials(args: Namespace) -> tuple[str, Any] | None:
    """把命令行参数解析为 (凭据类型, 凭据)

    档案 ID 与账号密码二选一；档案缺失、被禁用或字段为空时返回 None。
    """
    if getattr(args, "id", None):
        auto = profile.get_automation(args.id)
        if auto is None:
            logger.error(f"未找到档案 ID: {args.id}")
            return None
        if not auto.enabled:
            logger.warning(f"档案 {args.id} 已被禁用")
            return None

        match auto:
            case EasiAutomation():
                if auto.account == "":
                    logger.error(f"档案 {args.id} 的账号为空")
                    return None
                if auto.password == "":
                    logger.error(f"档案 {args.id} 的密码为空")
                    return None
                return auto.type, (auto.account, auto.password)
        return None

    if args.account and args.password:
        return "password", (args.account, args.password)

    logger.error("参数错误: 使用 --account 时必须同时提供 --password")
    return None


def dispatch(launcher: Launcher, args: Namespace) -> None:
    """按子命令分发"""
    command = getattr(args, "command", None)
    match command:
        case "login":
            cmd_login(launcher, args)
        case "skip":
            cmd_skip(launcher)
        case "patch":
            cmd_patch(args)
        case "oobe":
            cmd_oobe(launcher)
        case "settings" | None:
            cmd_settings(launcher)
        case _:
            logger.debug(f"未知命令: {command!r}")


def cmd_login(launcher: Launcher, args: Namespace) -> None:
    """login 子命令 - 执行自动登录"""
    if not launcher.start_login(args):
        return
    if not launcher.ipc_context:
        stop(get_app().exec())


def cmd_settings(launcher: Launcher) -> None:
    """settings 子命令 - 打开设置界面"""
    navigate_to = launcher.run_oobe() if not config.Internal.IsOobeCompleted else None

    launcher.show_settings_window(navigate_to)

    if not launcher.ipc_context:
        stop(get_app().exec())


def cmd_oobe(launcher: Launcher) -> None:
    """oobe 子命令 - 重新运行首次设置向导"""
    logger.info("手动触发首次设置向导")
    config.Internal.IsOobeCompleted = False
    cmd_settings(launcher)


def cmd_skip(launcher: Launcher) -> None:
    """skip 子命令 - 跳过下一次登录"""
    config.Login.SkipOnce = True
    logger.success("已更新配置文件，下次登录将跳过")

    if not launcher.ipc_context:
        stop()


def cmd_patch(args: Namespace) -> None:
    """patch 子命令 - 修补/撤销修补希沃白板

    退出码: 20 = 成功, 21 = 操作失败, 22 = 未找到希沃白板路径, 29 = 未知异常.
    使用 20–29 区间，与其他退出码完全隔离，避免误判。
    """
    path, _ = resolve_easinote_path()
    if path is None:
        logger.error("未找到希沃白板路径")
        stop(PATCH_ERR_EASINOTE_NOT_FOUND)

    action = "修补" if args.on else "撤销修补"
    try:
        ok = patch_easinote(path) if args.on else unpatch_easinote(path)
    except Exception as e:
        logger.error(f"{action}希沃白板时发生异常: {e}")
        stop(PATCH_ERR_UNKNOWN)

    if ok:
        logger.success(f"{action}希沃白板成功")
        stop(PATCH_OK)
    else:
        logger.error(f"{action}希沃白板失败")
        stop(PATCH_ERR_OPERATION_FAILED)
