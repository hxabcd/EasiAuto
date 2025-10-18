import logging
import subprocess
import time
import winreg

import pyautogui

from config import LoginConfig
from utils import get_resource, switch_window_by_title


class Automator:
    def __init__(self, account: str, password: str, config: LoginConfig) -> None:
        self.account = account
        self.password = password
        self.config = config

    def restart_easinote(self):
        """重启希沃进程"""

        logging.info("尝试重启希沃进程")

        # 自动获取希沃白板安装路径
        if (path := self.config.easinote.path) == "auto":
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
        cmd_list.append(["taskkill", "/f", "/im", self.config.easinote.process_name])
        if self.config.kill_agent:
            cmd_list.append(["taskkill", "/f", "/im", "EasiAgent.exe"])

        # 终止希沃进程
        logging.info("终止进程")
        for command in cmd_list:
            logging.debug(f"命令：{' '.join(command)}")
            subprocess.run(command, shell=True)
        time.sleep(self.config.timeout.terminate)  # 等待终止

        # 启动希沃白板
        logging.info("启动程序")
        logging.debug(f"路径：{path}，参数：{self.config.easinote.args}")
        args = self.config.easinote.args
        if args != "":
            subprocess.Popen([path, *args.split(" ")])
        else:
            subprocess.Popen(path)
        time.sleep(self.config.timeout.launch)  # 等待启动

    def login(self):
        """自动登录"""

        logging.info("尝试自动登录")

        # 直接登录与4K适配
        path_suffix = ""
        if self.config.directly:
            path_suffix += "_direct"
        if self.config.is_4k:
            path_suffix += "_4k"
        scale = 2 if self.config.is_4k else 1

        # 获取资源图片
        button_img = get_resource("button%s.png" % path_suffix)
        button_img_selected = get_resource("button_selected%s.png" % path_suffix)
        checkbox_img = get_resource("checkbox%s.png" % path_suffix)

        # 进入登录界面
        if not self.config.directly:
            logging.info("点击进入登录界面")
            pyautogui.click(172 * scale, 1044 * scale)
            time.sleep(self.config.timeout.enter_login_ui)
        else:
            logging.info("直接进入登录界面")

        # 识别并点击账号登录按钮
        logging.info("尝试识别账号登录按钮")
        try:
            button_button = pyautogui.locateCenterOnScreen(button_img, confidence=0.8)
            assert button_button
            logging.info("识别到账号登录按钮，正在点击")
            pyautogui.click(button_button)
            time.sleep(self.config.timeout.switch_tab)
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
        logging.debug(f"账号：{self.account}")
        pyautogui.click(button_button.x, button_button.y + 70 * scale)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        pyautogui.typewrite(self.account)

        # 输入密码
        logging.info("尝试输入密码")
        logging.debug(f"密码：{self.password}")
        pyautogui.click(button_button.x, button_button.y + 134 * scale)
        pyautogui.typewrite(self.password)

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

    def run(self):
        self.restart_easinote()
        switch_window_by_title("希沃白板")
        self.login()
        logging.info("执行完毕")
