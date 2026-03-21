import time

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
        screen_size = get_screen_size()
        scale = get_scale()

        # 进入登录界面
        if config.Login.IsIwb:
            self.check_interruption()
            self.update_progress("进入登录界面")

            # 相对左下角，单独缩放
            x, y = config.Login.Position.EnterLogin
            if config.Login.Position.EnableScaling:
                x = x * scale
                y = screen_size[1] - (config.Login.Position.BaseSize[1] - y) * scale

            self.click(x, y)
            time.sleep(config.Login.Timeout.EnterLoginUI)

        # 切换至账号登录页
        self.check_interruption()
        self.update_progress("切换至账号登录页")

        self.click(self.resolve_position(config.Login.Position.AccountLoginTab))
        time.sleep(config.Login.Timeout.SwitchTab)

        # 输入账号
        self.check_interruption()
        self.update_progress("输入账号")

        self.click(self.resolve_position(config.Login.Position.AccountInput))
        self.input(self.account)

        # 输入密码
        self.check_interruption()
        self.update_progress("输入密码")

        self.click(self.resolve_position(config.Login.Position.PasswordInput))
        self.input(self.password)

        # 勾选同意用户协议
        self.check_interruption()
        self.update_progress("勾选同意用户协议")

        self.click(self.resolve_position(config.Login.Position.AgreementCheckbox))

        # 点击登录按钮
        self.check_interruption()
        self.update_progress("点击登录按钮")

        self.press("enter")
