import time

from loguru import logger

from EasiAuto.common.config import config
from EasiAuto.common.utils import (
    Point,
    calc_relative_login_window_position,
    get_scale,
    get_screen_size,
)

from .base import PyAutoGuiBaseAutomator


class FixedAutomator(PyAutoGuiBaseAutomator):
    """通过固定位置来登录"""

    def resolve_position(self, position: tuple[int, int]) -> tuple[int, int]:
        """计算登录窗口内坐标的缩放，若设置未启用则返回原坐标"""

        if not config.Login.Position.EnableScaling:
            return position

        point = calc_relative_login_window_position(
            Point(position),
            window_size=config.Login.Position.LoginWindowSize,
            base_size=config.Login.Position.BaseSize,
        )

        return point.x, point.y

    def login(self):

        logger.info("尝试自动登录")
        self.task_update.emit("正在自动登录")

        screen_size = get_screen_size()
        scale = get_scale()

        # 进入登录界面
        self.check_interruption()
        if not config.Login.Directly:
            logger.info("点击进入登录界面")
            self.progress_update.emit("进入登录界面")

            # 相对左下角，单独缩放
            x, y = config.Login.Position.EnterLogin
            if config.Login.Position.EnableScaling:
                x = x * scale
                y = screen_size[1] - (config.Login.Position.BaseSize[1] - y) * scale

            self.click(x, y)
            time.sleep(config.Login.Timeout.EnterLoginUI)
        else:
            logger.info("直接进入登录界面")

        # 切换至账号登录页
        self.check_interruption()
        logger.info("切换至账号登录页")
        self.progress_update.emit("切换至账号登录页")
        self.click(self.resolve_position(config.Login.Position.AccountLoginTab))
        time.sleep(config.Login.Timeout.SwitchTab)

        # 输入账号
        self.check_interruption()
        logger.info("输入账号")
        self.progress_update.emit("输入账号")
        logger.debug(f"账号：{self.account}")
        self.click(self.resolve_position(config.Login.Position.AccountInput))
        self.input(self.account)

        # 输入密码
        self.check_interruption()
        logger.info("输入密码")
        self.progress_update.emit("输入密码")
        logger.debug(f"密码：{self.safe_for_log_password}")
        self.click(self.resolve_position(config.Login.Position.PasswordInput))
        self.input(self.password)

        # 勾选同意用户协议
        self.check_interruption()
        logger.info("勾选同意用户协议")
        self.progress_update.emit("勾选同意用户协议")
        self.click(self.resolve_position(config.Login.Position.AgreementCheckbox))

        # 点击登录按钮
        self.check_interruption()
        logger.info("点击登录按钮")
        self.progress_update.emit("点击登录")
        self.press("enter")

        self.progress_update.emit("登录完成")
        self.task_update.emit("完成")
