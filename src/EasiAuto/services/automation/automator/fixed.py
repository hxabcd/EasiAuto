import time

from EasiAuto.core.display import (
    Point,
    calc_relative_login_window_position,
    get_scale,
    get_screen_size_physical,
)
from EasiAuto.integrations.easinote.env import detect_is_iwb, parse_start_mode
from EasiAuto.models.config import config

from .pyautogui_base import PyAutoGuiBaseAutomator


class FixedAutomator(PyAutoGuiBaseAutomator):
    """通过固定位置来登录

    NOTE: 坐标基于白板（IWB）界面的登录窗口，故在机器本身不会进入白板界面时，
    强制追加 `-m Display iwb`，使希沃白板呈现该登录窗口；本身即为白板设备时沿用用户设置的参数。
    """

    def resolve_launch_args(self) -> str:
        args = config.Login.EasiNote.Args
        # 固定位置的坐标基于白板界面的登录窗口，故仅在确实会进入该界面时沿用用户参数
        mode = parse_start_mode(args)
        if mode == "display" or (mode is None and detect_is_iwb()):
            return args
        return "-m Display iwb"

    @staticmethod
    def resolve_position(position: tuple[int, int]) -> tuple[int, int]:
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
        screen_size = get_screen_size_physical()
        scale = get_scale()

        # 进入登录界面
        self.check_interruption()
        self.update_progress("进入登录界面")

        # 相对左下角，单独缩放
        x, y = config.Login.Position.EnterLogin
        if config.Login.Position.EnableScaling:
            x = x * scale
            y = screen_size[1] - (config.Login.Position.BaseSize[1] - y) * scale

        self.click(x, y)
        time.sleep(config.Login.Timeout.EnterLoginUI)

        # 显示隐私保护遮罩
        if config.Experimental.PrivacyMask.Enabled:
            x, y = FixedAutomator.resolve_position(config.Experimental.PrivacyMask.MaskLeftTop)
            w, h = Point(config.Experimental.PrivacyMask.MaskSize).scaled()
            self.show_privacy_mask(x, y, w, h)

        # 切换至账号登录页
        self.check_interruption()
        self.update_progress("切换至账号登录页")

        self.click(FixedAutomator.resolve_position(config.Login.Position.AccountLoginTab))
        time.sleep(config.Login.Timeout.SwitchTab)

        # 输入账号
        self.check_interruption()
        self.update_progress("输入账号")

        self.click(FixedAutomator.resolve_position(config.Login.Position.AccountInput))
        self.input(self.account)

        # 输入密码
        self.check_interruption()
        self.update_progress("输入密码")

        self.click(FixedAutomator.resolve_position(config.Login.Position.PasswordInput))
        self.input(self.password, is_secret=True)

        # 勾选同意用户协议
        self.check_interruption()
        self.update_progress("勾选同意用户协议")

        self.click(FixedAutomator.resolve_position(config.Login.Position.AgreementCheckbox))

        # 点击登录按钮
        self.check_interruption()
        self.update_progress("点击登录按钮")

        self.press("enter")
