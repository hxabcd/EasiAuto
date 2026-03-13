import time

import pyautogui
from loguru import logger

from EasiAuto.common.config import config
from EasiAuto.common.consts import IS_FULL
from EasiAuto.common.utils import get_resource
from EasiAuto.core.automation.base import BaseAutomator, safe_input


class CVAutomator(BaseAutomator):
    """通过识别图像登录"""

    def login(self):
        logger.info("尝试自动登录")
        self.task_update.emit("正在自动登录")

        # 直接登录与4K适配
        path_suffix = ""
        if config.Login.Directly:
            path_suffix += "_direct"
        if config.Login.Is4K:
            path_suffix += "_4k"
        path_suffix += ".png"
        scale = 2 if config.Login.Is4K else 1

        # 获取资源图片
        button_img = get_resource("EasiNoteUI/button" + path_suffix)
        button_img_selected = get_resource("EasiNoteUI/button_selected" + path_suffix)
        checkbox_img = get_resource("EasiNoteUI/checkbox" + path_suffix)

        # 进入登录界面
        self.check()
        if not config.Login.Directly:
            logger.info("点击进入登录界面")
            self.progress_update.emit("进入登录界面")

            pyautogui.click(172 * scale, 1044 * scale)
            time.sleep(config.Login.Timeout.EnterLoginUI)
        else:
            logger.info("直接进入登录界面")

        # 识别并点击账号登录按钮
        self.check()
        logger.info("尝试识别账号登录按钮")
        self.progress_update.emit("切换至账号登录页")

        try:
            if IS_FULL:
                button_button = pyautogui.locateCenterOnScreen(button_img, confidence=0.8)
            else:
                button_button = pyautogui.locateCenterOnScreen(button_img)
            assert button_button
            logger.info("识别到账号登录按钮，正在点击")
            pyautogui.click(button_button)
            time.sleep(config.Login.Timeout.SwitchTab)
        except (pyautogui.ImageNotFoundException, AssertionError):
            logger.warning("未能识别到账号登录按钮，尝试识别已选中样式")
            try:
                if IS_FULL:
                    button_button = pyautogui.locateCenterOnScreen(button_img_selected, confidence=0.8)
                else:
                    button_button = pyautogui.locateCenterOnScreen(button_img_selected)
                assert button_button
            except (pyautogui.ImageNotFoundException, AssertionError) as e:
                logger.error("未能识别到账号登录按钮")
                raise e

        # 输入账号
        self.check()
        logger.info("尝试输入账号")
        self.progress_update.emit("输入账号")
        logger.debug(f"账号：{self.account}")

        pyautogui.click(button_button.x, button_button.y + 70 * scale)
        safe_input(self.account)

        # 输入密码
        self.check()
        logger.info("尝试输入密码")
        self.progress_update.emit("输入密码")
        logger.debug(f"密码：{self.safe_for_log_password}")

        pyautogui.click(button_button.x, button_button.y + 134 * scale)
        safe_input(self.password)

        # 识别并勾选用户协议复选框
        self.check()
        logger.info("尝试识别用户协议复选框")
        self.progress_update.emit("勾选同意用户协议")

        try:
            if IS_FULL:
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
        self.check()
        logger.info("点击登录按钮")
        self.progress_update.emit("点击登录")
        pyautogui.press("enter")

        self.progress_update.emit("登录完成")
        self.task_update.emit("完成")
