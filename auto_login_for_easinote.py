"""自动登录希沃白板"""

import asyncio
import json
import os
import subprocess
import sys
import time
import winreg
from argparse import ArgumentParser

import pyautogui
import win11toast
from retry import retry

from default_config import DEFAULT_CONFIG

debug = False


def logger(text: str):
    """日志输出"""
    if debug:
        print(text)


def get_resource(file: str):
    """获取资源路径"""
    if hasattr(sys, "frozen"):
        base_path = getattr(sys, "_MEIPASS")
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "resources", file)


def load_config(path: str):
    """加载配置文件"""
    if not os.path.exists(path):
        logger(f"配置文件 {path} 不存在，自动创建")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)

    with open(path, "r", encoding="utf-8") as f:
        logger(f"载入配置文件：{path}")
        config = json.load(f)
        return config


async def show_warning():
    """显示警告通知"""

    logger("尝试显示警告通知")

    async def empty_func(*args):
        return args

    async def toast():
        return await win11toast.toast_async(
            "即将退出并重新登录希沃白板",
            buttons=["取消", "忽略"],
            duration="long",
            on_click=empty_func,
            on_dismissed=empty_func,
            on_failed=empty_func,
        )

    async def sleep():
        await asyncio.sleep(15)
        return "Time out"

    # 创建异步任务，检测超时
    task1 = asyncio.create_task(toast())
    task2 = asyncio.create_task(sleep())

    done, pending = await asyncio.wait(
        [task1, task2], return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()

    for task in done:
        try:
            result = await task
            if isinstance(result, dict) and result["arguments"] == "http:取消":
                logger("用户取消执行，正在退出")
                exit(0)
            else:
                logger("警告超时或忽略，继续执行")
                win11toast.clear_toast()
        except asyncio.CancelledError:
            logger(f"错误：任务 {task} 已取消")


def restart_easinote(path="auto", process_name="EasiNote.exe", args=""):
    """重启希沃进程"""

    logger("尝试重启希沃进程")

    # 自动获取希沃白板安装路径
    if path == "auto":
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Seewo\EasiNote5",
            ) as key:
                path = winreg.QueryValueEx(key, "ExePath")[0]
                logger(f"自动获取到路径：{path}")
        except Exception:
            logger("自动获取路径失败，使用默认路径")
            path = (
                r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe"
            )

    # 添加额外参数
    if args:
        path = f'"{path}" {args}'

    command = f"taskkill /f /im {process_name}"

    # 终止希沃进程
    logger(f"终止进程：{command}")
    os.system(command)
    time.sleep(1)  # 等待终止

    # 启动希沃白板
    logger(f"启动程序：{path}")
    subprocess.Popen(path, shell=True)
    time.sleep(8)  # 等待启动


def login(account: str, password: str, is_4k=False, directly=False):
    """自动登录"""

    logger("尝试自动登录")

    # 直接登录与4K适配
    path_suffix = ""
    if directly:
        path_suffix += "_direct"
    if is_4k:
        path_suffix += "_4k"
    scale = 2 if is_4k else 1

    # 获取资源图片
    account_login_img = get_resource("account_login%s.png" % path_suffix)
    account_login_img_selected = get_resource(
        "account_login_selected%s.png" % path_suffix
    )
    agree_checkbox_img = get_resource("agree_checkbox.png")

    # 进入登录界面
    if not directly:
        logger("点击进入登录界面")
        pyautogui.click(172 * scale, 1044 * scale)
        time.sleep(3)
    else:
        logger("直接进入登录界面")

    # 识别并点击账号登录按钮
    logger("尝试识别账号登录按钮")
    try:
        account_login_button = pyautogui.locateCenterOnScreen(
            # account_login_img, confidence=0.8
            account_login_img
        )
        assert account_login_button
        logger("识别到账号登录按钮，正在点击")
        pyautogui.click(account_login_button)
        time.sleep(1)
    except (pyautogui.ImageNotFoundException, AssertionError):
        logger("未能识别到账号登录按钮，尝试识别已选中样式")
        try:
            account_login_button = pyautogui.locateCenterOnScreen(
                # account_login_img_selected, confidence=0.8
                account_login_img_selected
            )
            assert account_login_button
        except (pyautogui.ImageNotFoundException, AssertionError) as e:
            logger("未能识别到已选中样式，正在退出")
            raise e

    # 输入账号
    logger(f"尝试输入账号：{account}")
    pyautogui.click(account_login_button.x, account_login_button.y + 70 * scale)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("backspace")
    pyautogui.typewrite(account)

    # 输入密码
    logger(f"尝试输入密码：{password}")
    pyautogui.click(account_login_button.x, account_login_button.y + 134 * scale)
    pyautogui.typewrite(password)

    # 识别并勾选用户协议复选框
    logger("尝试识别用户协议复选框")
    try:
        agree_checkbox = pyautogui.locateCenterOnScreen(
            # agree_checkbox_img, confidence=0.8
            agree_checkbox_img
        )
        assert agree_checkbox
    except (pyautogui.ImageNotFoundException, AssertionError) as e:
        logger("未能识别到用户协议复选框，正在退出")
        raise e

    logger("识别到用户协议复选框，正在点击")
    pyautogui.click(agree_checkbox)

    # 点击登录按钮
    logger("点击登录按钮")
    pyautogui.click(account_login_button.x, account_login_button.y + 198 * scale)


@retry(tries=2, delay=1)
def main(args):
    """执行自动登录"""

    # 加载配置文件
    config = load_config("config.json")
    global debug
    debug = config["debug_mode"]

    # 显示调试信息
    if config["debug_mode"]:
        print("已启用调试模式")
        print("传入的参数:")
        for key, value in vars(args).items():
            print(f" - {key}: {value}")
        print("载入的配置:")
        for key, value in config.items():
            print(f" - {key}: {value}")

    # 显示警告
    if config["show_warning"]:
        try:
            asyncio.run(show_warning())
        except Exception:
            logger("显示警告通知时出错，跳过警告")

    # 执行操作
    restart_easinote(**config["easinote"])
    login(
        args.account,
        args.password,
        is_4k=config["4k_mode"],
        directly=config["login_directly"],
    )

    logger("执行完毕")
    return 0


if __name__ == "__main__":
    # 解析命令行参数
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("-a", "--account", type=str, required=True, help="账号")
    parser.add_argument("-p", "--password", type=str, required=True, help="密码")
    args = parser.parse_args()
    main(args)
