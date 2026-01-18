import subprocess
import time
import winreg
from abc import ABCMeta, abstractmethod

import win32gui
from loguru import logger
from PySide6.QtCore import QThread, Signal

from config import LoginConfig
from utils import get_resource, switch_window


class QABCMeta(type(QThread), ABCMeta):  # type: ignore
    pass  # QThread 与抽象基类的兼容元类


class BaseAutomator(QThread, metaclass=QABCMeta):
    finished = Signal(str)
    task_update = Signal(str)
    progress_update = Signal(str)

    def __init__(self, account: str, password: str, config: LoginConfig, max_retries: int = 2) -> None:
        super().__init__()
        self.account = account
        self.password = password
        self.config = config
        self.max_retries = max_retries

    def restart_easinote(self):
        """重启希沃进程"""

        logger.info("尝试重启希沃进程")
        self.task_update.emit("重启希沃进程")

        # 自动获取希沃白板安装路径
        if self.config.EasiNote.AutoPath:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\WOW6432Node\Seewo\EasiNote5",
                ) as key:
                    path = winreg.QueryValueEx(key, "ExePath")[0]
                    logger.debug("自动获取到路径")
            except Exception:
                logger.warning("自动获取路径失败，使用默认路径")
                path = r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe"
        else:
            path = self.config.EasiNote.Path
        logger.debug(f"路径：{path}")

        # 终止希沃进程
        logger.info("终止进程")
        self.progress_update.emit("终止希沃白板进程")

        cmd_list = [["taskkill", "/f", "/im", self.config.EasiNote.ProcessName]]
        if self.config.KillAgent:
            cmd_list.append(["taskkill", "/f", "/im", "EasiAgent.exe"])

        for command in cmd_list:
            logger.debug(f"命令：{' '.join(command)}")
            subprocess.run(command, shell=True, check=False)
        time.sleep(self.config.Timeout.Terminate)  # 等待终止

        # 启动希沃白板
        logger.info("启动程序")
        self.progress_update.emit("等待程序启动")
        logger.debug(f"路径：{path}，参数：{self.config.EasiNote.Args}")

        args = self.config.EasiNote.Args
        import os

        if not os.path.exists(path):
            logger.error(f"希沃白板可执行文件不存在: {path}")
            raise FileNotFoundError(f"希沃白板可执行文件不存在: {path}")

        subprocess.Popen([path, *args.split(" ")] if args != "" else path)

        # 轮询窗口是否打开
        window_title = self.config.EasiNote.WindowTitle  # 需要提前配置窗口标题
        timeout = self.config.Timeout.LaunchPollingTimeout  # 最长等待时间
        interval = self.config.Timeout.LaunchPollingInterval  # 轮询间隔秒

        elapsed = 0
        logger.info(f"等待窗口 {window_title} 打开...")

        while elapsed < timeout:
            self.hwnd = win32gui.FindWindow(None, window_title)
            if self.hwnd:
                logger.success(f"窗口已打开：{window_title}")
                self.task_update.emit("等待登录")
                self.progress_update.emit("希沃白板已启动")

                time.sleep(self.config.Timeout.AfterLaunch)
                switch_window(self.hwnd)
                return
            time.sleep(interval)
            elapsed += interval
        logger.error(f"窗口在 {timeout} 秒内未打开：{window_title}")
        raise TimeoutError(f"窗口在 {timeout} 秒内未打开：{window_title}")

    @abstractmethod
    def login(self):
        """自动登录"""
        ...

    def run(self):
        """完整登录流程"""
        retries = 0
        while True:
            try:
                self.restart_easinote()
                self.login()

                self.finished.emit("登录完成")
                return
            except BaseException as e:
                import sys

                from utils import log_exception

                retries += 1
                log_exception(*sys.exc_info(), prefix=f"登录子线程发生异常（尝试 {retries}/{self.max_retries}）")  # type: ignore

                if retries <= self.max_retries:
                    logger.error(f"登录过程中发生错误 ({type(e).__name__}): {e}")
                    logger.warning(f"将在2s后重试（尝试 {retries}/{self.max_retries}）")
                    time.sleep(2)
                else:
                    logger.critical(f"{retries}次尝试均登录失败: {e}")
                    self.finished.emit(f"登录失败: {e}")
                    return


class CVAutomator(BaseAutomator):
    """
    使用 OpenCV 识别图像来登录
    需要存在 PyAutoGUI 才能调用
    """

    def login(self):
        import pyautogui

        try:
            import cv2  # noqa: F401

            use_opencv = True
        except ImportError:
            logger.warning("无法导入 OpenCV，回退到基本识别")
            use_opencv = False

        logger.info("尝试自动登录")
        self.task_update.emit("自动登录")

        # 直接登录与4K适配
        path_suffix = ""
        if self.config.Directly:
            path_suffix += "_direct"
        if self.config.Is4K:
            path_suffix += "_4k"
        scale = 2 if self.config.Is4K else 1

        # 获取资源图片
        button_img = get_resource(f"button{path_suffix}.png")
        button_img_selected = get_resource(f"button_selected{path_suffix}.png")
        checkbox_img = get_resource(f"checkbox{path_suffix}.png")

        # 进入登录界面
        if not self.config.Directly:
            logger.info("点击进入登录界面")
            self.progress_update.emit("进入登录界面")

            pyautogui.click(172 * scale, 1044 * scale)
            time.sleep(self.config.Timeout.EnterLoginUI)
        else:
            logger.info("直接进入登录界面")

        # 识别并点击账号登录按钮
        logger.info("尝试识别账号登录按钮")
        self.progress_update.emit("切换至账号登录页")

        try:
            if use_opencv:
                button_button = pyautogui.locateCenterOnScreen(button_img, confidence=0.8)
            else:
                button_button = pyautogui.locateCenterOnScreen(button_img)
            assert button_button
            logger.info("识别到账号登录按钮，正在点击")
            pyautogui.click(button_button)
            time.sleep(self.config.Timeout.SwitchTab)
        except (pyautogui.ImageNotFoundException, AssertionError):
            logger.warning("未能识别到账号登录按钮，尝试识别已选中样式")
            try:
                if use_opencv:
                    button_button = pyautogui.locateCenterOnScreen(button_img_selected, confidence=0.8)
                else:
                    button_button = pyautogui.locateCenterOnScreen(button_img_selected)
                assert button_button
            except (pyautogui.ImageNotFoundException, AssertionError) as e:
                logger.error("未能识别到账号登录按钮")
                raise e

        # 输入账号
        logger.info("尝试输入账号")
        self.progress_update.emit("输入账号")
        logger.debug(f"账号：{self.account}")

        pyautogui.click(button_button.x, button_button.y + 70 * scale)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        pyautogui.typewrite(self.account)

        # 输入密码
        logger.info("尝试输入密码")
        self.progress_update.emit("输入密码")
        logger.debug(f"密码：{self.password}")

        pyautogui.click(button_button.x, button_button.y + 134 * scale)
        pyautogui.typewrite(self.password)

        # 识别并勾选用户协议复选框
        logger.info("尝试识别用户协议复选框")
        self.progress_update.emit("勾选同意用户协议")

        try:
            if use_opencv:
                agree_checkbox = pyautogui.locateCenterOnScreen(checkbox_img, confidence=0.8)
            else:
                agree_checkbox = pyautogui.locateCenterOnScreen(checkbox_img)
            assert agree_checkbox
        except (pyautogui.ImageNotFoundException, AssertionError) as e:
            logger.error("未能识别到用户协议复选框")
            raise e

        logger.info("识别到用户协议复选框，正在点击")
        pyautogui.click(agree_checkbox)

        # 点击登录按钮
        logger.info("点击登录按钮")
        self.progress_update.emit("点击登录")

        pyautogui.click(button_button.x, button_button.y + 198 * scale)

        self.progress_update.emit("登录完成")
        self.task_update.emit("完成")


class FixedAutomator(BaseAutomator):
    """通过固定位置来登录"""

    def login(self): ...  # 待实现/移除


class UIAAutomator(BaseAutomator):
    """
    通过 UI Automation 自动定位组件位置来登录
    需要存在 PyWinAuto 才能调用
    """

    def login(self):
        from pywinauto import Application, Desktop

        logger.info("尝试自动登录")
        self.task_update.emit("自动登录")

        # 连接至希沃白板
        logger.info("连接 UI Automation 后端至希沃白板")
        self.progress_update.emit("连接后端至希沃白板")

        app = Application(backend="uia").connect(handle=self.hwnd)
        dlg = app.window(title="希沃白板")
        dlg.set_focus()  # 设置焦点为希沃白板窗口

        # 如果启动进入白板 (iwb)
        is_iwb = not self.config.Directly
        if is_iwb:
            # 先进入登录界面
            logger.info("点击进入登录界面")
            self.progress_update.emit("进入登录界面")

            iwb_login_button = dlg.child_window(auto_id="ProfileButton", control_type="Button")
            iwb_login_button.click()
            time.sleep(self.config.Timeout.EnterLoginUI)

            # 切换操作窗口为弹出的 IWBLogin
            logger.info("切换到登录界面")
            self.progress_update.emit("切换后端至登录界面")

            dlg = Desktop(backend="uia").window(auto_id="IWBLogin")

        # 切换至账号登录
        logger.info("定位并点击账号登录按钮")
        self.progress_update.emit("切换至账号登录页")

        account_login_button = dlg.child_window(
            auto_id="AccountRadioButton" if is_iwb else "AccountLoginRadioButton", control_type="RadioButton"
        )
        account_login_button.click()
        time.sleep(self.config.Timeout.SwitchTab)

        # 定位登录控件
        logger.info("定位登录控件")
        account_login_page = dlg.child_window(
            auto_id="IwbAccountControl" if is_iwb else "PasswordLoginControl", control_type="Custom"
        )

        # 输入账号
        logger.info("定位输入框并填入账号")
        self.progress_update.emit("输入账号")
        logger.debug(f"账号：{self.account}")

        account_input = account_login_page.ComboBox.Edit
        account_input.set_edit_text(self.account)

        # 输入密码
        logger.info("定位输入框并填入密码")
        self.progress_update.emit("输入密码")
        logger.debug(f"密码：{self.password}")
        password_input = account_login_page.child_window(auto_id="PasswordBox", control_type="Edit")
        password_input.set_edit_text(self.password)

        # 勾选同意用户协议
        logger.info("定位用户协议复选框并勾选")
        self.progress_update.emit("勾选同意用户协议")

        agreement_button = account_login_page.child_window(auto_id="AgreementCheckBox", control_type="CheckBox")
        if not agreement_button.get_toggle_state():
            agreement_button.toggle()

        # 登录
        logger.info("点击登录按钮")
        self.progress_update.emit("点击登录")

        login_button = account_login_page.child_window(auto_id="LoginButton", control_type="Button")
        login_button.click()

        self.progress_update.emit("登录完成")
        self.task_update.emit("完成")
