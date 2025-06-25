"""自动登录希沃白板"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time

import pyautogui
import win11toast
from retry import retry

from default_config import DEFAULT_CONFIG

debug = False


def logger(text: str):
    """日志输出"""
    if debug:
        print(text)


def get_resource(file):
    """获取资源路径"""
    if hasattr(sys, "frozen"):
        base_path = getattr(sys, "_MEIPASS")
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "resources", file)


def load_config(path):
    """加载配置文件"""
    if not os.path.exists(path):
        logger(f"配置文件 {path} 不存在，自动创建")
        with open(path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_CONFIG)

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


def restart_easinote(program_path, process_name="EasiNote.exe", args=""):
    """重启希沃进程"""

    logger("尝试重启希沃进程")

    command = f"taskkill /f /im {process_name}"

    # 终止希沃进程
    logger(f"终止进程：{command}")
    os.system(command)
    time.sleep(1)  # 等待终止

    # 启动希沃白板
    logger(f"启动程序：{program_path}")
    subprocess.Popen([program_path], shell=True)
    time.sleep(8)  # 等待启动


def login(account, password, is_4k=False, directly=False):
    """自动登录"""

    logger("尝试自动登录")

    # 4K 适配
    if is_4k:
        logger("已启用 4K 适配")
        scale = 2
        account_login_img = get_resource("account_login_4k.png")
        account_login_img_selected = get_resource("account_login_selected_4k.png")
        agree_checkbox_img = get_resource("agree_checkbox_4k.png")
    else:
        logger("未启用 4K 适配")
        scale = 1
        account_login_img = get_resource("account_login.png")
        account_login_img_selected = get_resource("account_login_selected.png")
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
            account_login_img, confidence=0.8
        )
        assert account_login_button
        logger("识别到账号登录按钮，正在点击")
        pyautogui.click(account_login_button)
        time.sleep(1)
    except (pyautogui.ImageNotFoundException, AssertionError) as e:
        logger("未能识别到账号登录按钮，尝试识别已选中样式")
        account_login_button = pyautogui.locateCenterOnScreen(
            account_login_img_selected, confidence=0.8
        )
        if not account_login_button:
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
            agree_checkbox_img, confidence=0.8
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
        asyncio.run(show_warning())

    # 执行操作
    restart_easinote(*config["easinote"])
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-a", "--account", type=str, required=True, help="账号")
    parser.add_argument("-p", "--password", type=str, required=True, help="密码")
    args = parser.parse_args()
    main(args)
