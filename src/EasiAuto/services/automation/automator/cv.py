import time

from loguru import logger

from EasiAuto.core.display import Point, get_scale, get_screen_size_physical
from EasiAuto.core.resources import get_resource
from EasiAuto.models.config import config

from .errors import LoginError
from .pyautogui_base import PyAutoGuiBaseAutomator

# 模板图仅按以下显示环境采集，其余环境无法保证像素匹配
# (物理分辨率, 缩放, 资源后缀)
_IMAGE_ENVIRONMENTS: tuple[tuple[tuple[int, int], float, str], ...] = (
    ((1920, 1080), 1.0, ""),
    ((3840, 2160), 2.0, "_4k"),
)


def resolve_image_variant(size: tuple[int, int], scale: float) -> str:
    """按当前显示环境选择模板图变体

    Args:
        size (tuple[int, int]): 屏幕物理分辨率
        scale (float): 系统缩放比例

    Returns:
        str: 资源后缀，`""` 或 `"_4k"`

    Raises:
        LoginError: 当前分辨率与缩放无对应模板图
    """
    for env_size, env_scale, suffix in _IMAGE_ENVIRONMENTS:
        if size == env_size and abs(scale - env_scale) < 0.01:
            return suffix

    supported = "、".join(f"{w}x{h} {round(s * 100)}%" for (w, h), s, _ in _IMAGE_ENVIRONMENTS)
    detected = f"{size[0]}x{size[1]} {round(scale * 100)}%"
    raise LoginError(f"当前显示环境 {detected} 不受图像识别支持，仅支持 {supported}", retry=False)


class CvAutomator(PyAutoGuiBaseAutomator):
    """通过识别图像登录

    NOTE: 模板图仅覆盖 1920x1080 100% 与 3840x2160 200% 两套环境，
    其余环境在启动希沃白板前即判定为不可用。
    """

    def __init__(self, account: str, password: str) -> None:
        super().__init__(account, password)
        self._variant: str = ""

    def before_prepare(self):
        size = get_screen_size_physical()
        scale = get_scale()
        self._variant = resolve_image_variant(size, scale)
        logger.info(
            f"图像识别显示环境: {size[0]}x{size[1]} {round(scale * 100)}% ({'4K' if self._variant else '默认'}模板)"
        )

    @property
    def path_suffix(self) -> str:
        """图像资源后缀，随界面环境（白板/普通）与分辨率适配变化"""
        suffix = "" if self.is_iwb else "_direct"
        return suffix + self._variant

    def find_control(self, img_name: str, ext_name: str = "png", _assert: bool = False) -> Point:
        import pyautogui

        img = get_resource(f"EasiNoteUI/{img_name}{self.path_suffix}.{ext_name}")

        try:
            control = pyautogui.locateCenterOnScreen(img)
            assert control is not None
        except (pyautogui.ImageNotFoundException, AssertionError) as e:
            raise LoginError(f"未识别到控件: {img_name}") from e

        return Point(control.x, control.y)

    def login(self):
        scale = get_scale()

        # 进入登录界面
        self.check_interruption()
        if self.is_iwb:
            self.update_progress("进入登录界面")

            self.click(172 * scale, 1044 * scale)
            time.sleep(config.Login.Timeout.EnterLoginUI)

        # 切换至账号登录页
        self.check_interruption()
        self.update_progress("切换至账号登录页")

        try:
            account_login_button = self.find_control("account_login_button")
            self.click(account_login_button)
            time.sleep(config.Login.Timeout.SwitchTab)
        except LoginError:
            logger.warning("未能识别到账号登录按钮, 尝试识别已选中样式")
            account_login_button = self.find_control("account_login_button")

        # 输入账号
        self.check_interruption()
        self.update_progress("输入账号")

        self.click(account_login_button.x, account_login_button.y + 70 * scale)
        self.input(self.account)

        # 输入密码
        self.check_interruption()
        self.update_progress("输入密码")

        self.click(account_login_button.x, account_login_button.y + 134 * scale)
        self.input(self.password, is_secret=True)

        # 勾选同意用户协议
        self.check_interruption()
        self.update_progress("勾选同意用户协议")

        agree_checkbox = self.find_control("agreement_checkbox")
        self.click(agree_checkbox)

        # 点击登录按钮
        self.check_interruption()
        self.update_progress("点击登录按钮")

        self.press("enter")
