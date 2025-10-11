import logging
import multiprocessing
import os
import subprocess
import sys
import time
import winreg
from argparse import ArgumentParser
from pathlib import Path

import pyautogui
import win32con
import win32gui
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_fixed

from banner import WarningBanner
from config import Config, LoginConfig, get_log_level

logger = logging.getLogger(__name__)


def set_logger(level=logging.WARNING):
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


def get_resource(file: str):
    """获取资源路径"""
    if hasattr(sys, "frozen"):
        base_path = getattr(sys, "_MEIPASS")
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "resources", file)


def load_config(config_file="config.json") -> Config:
    """加载配置文件"""
    exe_dir = Path(sys.argv[0]).resolve().parent
    config_path = exe_dir / config_file

    logging.debug(f"查找配置文件: {config_path}")
    # 若配置文件存在则加载，否则创建默认配置文件并退出
    if config_path.exists():
        return Config.load(str(config_path))
    else:
        logging.warning(f"配置文件 {config_path} 不存在，自动创建")
        config = Config.load(str(config_path))
        config.save()
        time.sleep(3)
        sys.exit(0)


def init():
    """初始化"""
    set_logger()

    global config
    config = load_config()

    try:
        set_logger(get_log_level[config.app.log_level])
        logging.info(f"当前日志级别：{config.app.log_level}")
    except ValueError:
        set_logger()
        logging.error(f"无效的日志级别：{config.app.log_level}，使用默认级别 WARNING")

    logging.info("初始化完成")

    # logging.debug(
    #     "载入的配置：\n%s" % "\n".join([f" - {key}: {value}" for key, value in config])
    # )
    # TODO: 嵌套格式无法正常打印


init()


def show_warning():
    """显示警告弹窗"""
    app = QApplication()
    msg_box = QMessageBox()
    msg_box.setWindowFlag(Qt.WindowStaysOnTopHint)  # 窗口置顶
    msg_box.setIcon(QMessageBox.Warning)
    msg_box.setWindowTitle("EasiAuto")
    msg_box.setWindowIcon(QIcon(get_resource("easiauto.ico")))
    msg_box.setText("<span style='font-size: 20px; font-weight: bold;'>即将运行希沃白板自动登录</span>")
    msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    msg_box.button(QMessageBox.Ok).setText("立即执行")
    msg_box.button(QMessageBox.Cancel).setText("取消")

    # 设置倒计时
    timeout: int = config.warning.timeout
    if timeout <= 0:
        timeout = 15

    # 更新倒计时文本
    def update_text():
        nonlocal timeout
        if timeout > 0:
            msg_box.setInformativeText(f"将在 {timeout} 秒后继续执行")
            timeout -= 1
        else:
            logging.info("等待超时")
            msg_box.button(QMessageBox.Ok).click()
            timer.stop()
            app.quit()
            return

    update_text()

    # 计时器
    timer = QTimer()
    timer.timeout.connect(update_text)
    timer.setInterval(1000)
    timer.start()

    result = msg_box.exec()

    if result == QMessageBox.Cancel:
        logging.info("用户取消操作，正在退出")
        sys.exit(0)

    logging.info("用户确认或超时，继续执行")
    timer.stop()
    app.quit()
    return


def show_banner():
    app = QApplication(sys.argv)
    screen = app.primaryScreen().geometry()
    w = WarningBanner(config.banner)
    w.setGeometry(0, 80, screen.width(), 140)  # 顶部横幅
    w.show()
    app.exec()


def restart_easinote(config: LoginConfig):
    """重启希沃进程"""

    logging.info("尝试重启希沃进程")

    # 自动获取希沃白板安装路径
    if (path := config.easinote.path) == "auto":
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Seewo\EasiNote5",
            ) as key:
                path = winreg.QueryValueEx(key, "ExePath")[0]
                logging.info("自动获取到路径")
        except Exception:
            logging.warning("自动获取路径失败，使用默认路径")
            path = r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe"
    logging.debug(f"路径：{path}")

    # 配置终止指令
    cmd_list = []
    if logging.getLogger().level not in [logging.DEBUG, logging.INFO]:
        cmd_list.append("@echo off")
    if config.kill_agent:
        cmd_list.append("taskkill /f /im EasiAgent.exe")
    cmd_list.append(f"taskkill /f /im {config.easinote.process_name}")
    
    command = "\n".join(cmd_list)

    # 终止希沃进程
    logging.info("终止进程")
    logging.debug(f"命令：{command}")
    os.system(command)
    time.sleep(config.timeout.terminate)  # 等待终止

    if config.kill_agent:
        os.system("taskkill /f /im EasiAgent.exe")

    # 启动希沃白板
    logging.info("启动程序")
    logging.debug(f"路径：{path}，参数：{config.easinote.args}")
    subprocess.Popen(f'"{path}" {config.easinote.args}', shell=True)
    time.sleep(config.timeout.launch)  # 等待启动


def switch_window_by_title(title):
    """通过窗口标题切换焦点"""

    def callback(hwnd, extra):
        if title in win32gui.GetWindowText(hwnd):
            extra.append(hwnd)

    hwnds = []
    # 枚举所有顶层窗口
    win32gui.EnumWindows(callback, hwnds)

    if hwnds:
        # 切换到找到的第一个窗口
        win32gui.ShowWindow(hwnds[0], win32con.SW_RESTORE)  # 确保窗口不是最小化状态
        win32gui.SetForegroundWindow(hwnds[0])  # 设置为前台窗口（获取焦点）
        logging.info(f"已切换到标题包含 '{title}' 的窗口")
    else:
        logging.warning(f"未找到标题包含 '{title}' 的窗口")


def login(account: str, password: str, config: LoginConfig):
    """自动登录"""

    logging.info("尝试自动登录")

    # 直接登录与4K适配
    path_suffix = ""
    if config.directly:
        path_suffix += "_direct"
    if config.is_4k:
        path_suffix += "_4k"
    scale = 2 if config.is_4k else 1

    # 获取资源图片
    button_img = get_resource("button%s.png" % path_suffix)
    button_img_selected = get_resource("button_selected%s.png" % path_suffix)
    checkbox_img = get_resource("checkbox%s.png" % path_suffix)

    # 进入登录界面
    if not config.directly:
        logging.info("点击进入登录界面")
        pyautogui.click(172 * scale, 1044 * scale)
        time.sleep(config.timeout.enter_login_ui)
    else:
        logging.info("直接进入登录界面")

    # 识别并点击账号登录按钮
    logging.info("尝试识别账号登录按钮")
    try:
        button_button = pyautogui.locateCenterOnScreen(button_img, confidence=0.8)
        assert button_button
        logging.info("识别到账号登录按钮，正在点击")
        pyautogui.click(button_button)
        time.sleep(config.timeout.switch_tab)
    except (pyautogui.ImageNotFoundException, AssertionError):
        logging.warning("未能识别到账号登录按钮，尝试识别已选中样式")
        try:
            button_button = pyautogui.locateCenterOnScreen(button_img_selected, confidence=0.8)
            assert button_button
        except (pyautogui.ImageNotFoundException, AssertionError) as e:
            logging.exception("未能识别到账号登录按钮")
            raise e

    # 输入账号
    logging.info("尝试输入账号")
    logging.debug(f"账号：{account}")
    pyautogui.click(button_button.x, button_button.y + 70 * scale)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("backspace")
    pyautogui.typewrite(account)

    # 输入密码
    logging.info("尝试输入密码")
    logging.debug(f"密码：{password}")
    pyautogui.click(button_button.x, button_button.y + 134 * scale)
    pyautogui.typewrite(password)

    # 识别并勾选用户协议复选框
    logging.info("尝试识别用户协议复选框")
    try:
        agree_checkbox = pyautogui.locateCenterOnScreen(checkbox_img, confidence=0.8)
        assert agree_checkbox
    except (pyautogui.ImageNotFoundException, AssertionError) as e:
        logging.exception("未能识别到用户协议复选框")
        raise e

    logging.info("识别到用户协议复选框，正在点击")
    pyautogui.click(agree_checkbox)

    # 点击登录按钮
    logging.info("点击登录按钮")
    pyautogui.click(button_button.x, button_button.y + 198 * scale)


@retry(
    stop=stop_after_attempt(config.app.max_retries + 1),
    wait=wait_fixed(2),
    before_sleep=before_sleep_log(logger, logging.ERROR),
)
def action(args):
    """完整自动登录操作"""
    restart_easinote(config.login)
    switch_window_by_title("希沃白板")
    login(args.account, args.password, config.login)

    logging.info("执行完毕")


def cmd_login(args):
    """执行自动登录"""

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
    action(args)

    sys.exit(0)


def cmd_setting(args):
    """打开设置界面"""
    ...  # 0.4 未实装内容


def cmd_skip(args):
    """跳过下一次登录"""
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

    # # setting 子命令
    # setting_parser = subparsers.add_parser("setting", help="打开设置界面")
    # setting_parser.set_defaults(func=cmd_setting)

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
