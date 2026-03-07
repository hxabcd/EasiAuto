import time

import pyautogui
from loguru import logger

from EasiAuto.common.config import config
from EasiAuto.common.utils import get_scale, get_screen_size
from EasiAuto.core.automation.base import BaseAutomator, safe_input

screen_size = get_screen_size()
scale = get_scale()


class FixedAutomator(BaseAutomator):
    """通过固定位置来登录"""

    def scale_in_window(self, position: tuple[int, int]) -> tuple[int, int]:
        """计算登录窗口内坐标的缩放，若设置未启用则返回原坐标"""

        if not config.Login.Position.EnableScaling:
            return position

        window_size = config.Login.Position.LoginWindowSize

        top_left_x = (config.Login.Position.BaseSize[0] - window_size[0]) / 2
        top_left_y = (config.Login.Position.BaseSize[1] - window_size[1]) / 2
        scaled_top_left_x = (screen_size[0] - window_size[0] * scale) / 2
        scaled_top_left_y = (screen_size[1] - window_size[1] * scale) / 2

        # -------- 实现原理 --------
        # (x - top_left_x) 获取基于登录窗口的相对位置
        # 乘以 scale 得到缩放后的相对位置
        # 加上 scaled_top_left_x 得到屏幕上的绝对位置
        x = (position[0] - top_left_x) * scale + scaled_top_left_x
        y = (position[1] - top_left_y) * scale + scaled_top_left_y

        return int(x), int(y)

    def login(self):

        logger.info("尝试自动登录")
        self.task_update.emit("自动登录")

        # 进入登录界面
        if not config.Login.Directly:
            logger.info("点击进入登录界面")
            self.progress_update.emit("进入登录界面")

            # 相对左下角，单独缩放
            x, y = config.Login.Position.EnterLogin
            if config.Login.Position.EnableScaling:
                x = x * scale
                y = screen_size[1] - (config.Login.Position.BaseSize[1] - y) * scale

            pyautogui.click(x, y)
            time.sleep(config.Login.Timeout.EnterLoginUI)
        else:
            logger.info("直接进入登录界面")

        # 切换至账号登录页
        logger.info("切换至账号登录页")
        self.progress_update.emit("切换至账号登录页")
        pyautogui.click(*self.scale_in_window(config.Login.Position.AccountLoginTab))
        time.sleep(config.Login.Timeout.SwitchTab)

        # 输入账号
        logger.info("输入账号")
        self.progress_update.emit("输入账号")
        logger.debug(f"账号：{self.account}")
        pyautogui.click(*self.scale_in_window(config.Login.Position.AccountInput))
        safe_input(self.account)

        # 输入密码
        logger.info("输入密码")
        self.progress_update.emit("输入密码")
        logger.debug(f"密码：{self.safe_for_log_password}")
        pyautogui.click(*self.scale_in_window(config.Login.Position.PasswordInput))
        safe_input(self.password)

        # 勾选同意用户协议
        logger.info("勾选同意用户协议")
        self.progress_update.emit("勾选同意用户协议")
        pyautogui.click(*self.scale_in_window(config.Login.Position.AgreementCheckbox))

        # 点击登录按钮
        logger.info("点击登录按钮")
        self.progress_update.emit("点击登录")
        pyautogui.press("enter")

        self.progress_update.emit("登录完成")
        self.task_update.emit("完成")
