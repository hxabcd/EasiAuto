"""显示几何：缩放比例、屏幕尺寸与刷新率、以及坐标换算工具。"""

from __future__ import annotations

from typing import cast, overload

from PySide6.QtWidgets import QApplication


def get_scale() -> float:
    """获取当前系统缩放比例"""
    app = cast(QApplication, QApplication.instance())
    if app is None:
        raise RuntimeError("QApplication 未初始化")
    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("无法获取主屏幕信息")
    return screen.devicePixelRatio()


def get_main_display_refresh_rate() -> int:
    """获取主显示器刷新率（Hz），限制在 [30, 240] 内；不可得时回退 60。

    动画帧率应跟随显示器，而不是使用固定值；异常/虚拟显示器可能出现
    离谱数值，因此做上下限约束。
    """
    app = cast(QApplication, QApplication.instance())
    if not app:
        return 60
    screen = app.primaryScreen()
    if screen is None:
        return 60
    try:
        rate = round(screen.refreshRate())
    except Exception:
        return 60
    return max(30, min(rate, 240))


def get_animation_frame_interval() -> int:
    """按主显示器刷新率计算动画帧间隔（毫秒），下限 1ms"""
    return max(1, int(1000 / get_main_display_refresh_rate()))


def get_screen_size() -> tuple[int, int]:
    """获取屏幕尺寸（逻辑坐标）"""
    app = cast(QApplication, QApplication.instance())
    if app is None:
        raise RuntimeError("QApplication 未初始化")
    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("无法获取主屏幕信息")

    geo = screen.geometry()
    return (geo.width(), geo.height())


def get_screen_size_physical() -> tuple[int, int]:
    """获取屏幕尺寸（物理像素）"""
    w, h = get_screen_size()
    scale = get_scale()
    return (int(w * scale), int(h * scale))


class Point:
    """一个点，描述屏幕上的坐标。坐标值恒为整数"""

    scale: float | None = None

    @overload
    def __init__(self, x: int | float, y: int | float) -> None: ...

    @overload
    def __init__(self, x: tuple[int | float, int | float]) -> None: ...

    def __init__(self, x: int | float | tuple[int | float, int | float], y: int | float | None = None):
        if isinstance(x, tuple):
            x_val, y_val = x
        else:
            if y is None:
                raise ValueError("必须传入 y 坐标或一个二元组")
            x_val, y_val = x, y

        if x_val < 0 or y_val < 0:
            raise ValueError("坐标值必须为非负数")

        self.x: int = int(x_val)
        self.y: int = int(y_val)

    def __add__(self, other: Point) -> Point:
        if not isinstance(other, Point):
            return NotImplemented
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Point) -> Point:
        if not isinstance(other, Point):
            return NotImplemented
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, other: int | float) -> Point:
        if not isinstance(other, (int, float)):
            return NotImplemented
        return Point(self.x * other, self.y * other)

    def __rmul__(self, other: int | float) -> Point:
        return self.__mul__(other)

    def __truediv__(self, other: int | float) -> Point:
        return self.__mul__(1 / other)

    def __iter__(self):
        yield self.x
        yield self.y

    def scaled(self) -> Point:
        """获取缩放后的坐标"""
        if Point.scale is None:
            Point.scale = get_scale()
        return Point(self.x * Point.scale, self.y * Point.scale)


def calc_relative_login_window_position(
    position: Point, window_size: tuple[int, int], base_size: tuple[int, int]
) -> Point:
    """计算相对登录窗口的位置

    Args:
        position (Point): 原始位置
        window_size (tuple[int, int]): 窗口大小
        base_size (tuple[int, int]): 原始位置与窗口大小所基于的屏幕分辨率
    """

    screen = Point(get_screen_size_physical())
    base_screen = Point(base_size)
    window = Point(window_size)
    window_position = (base_screen - window) / 2

    rel_position = position - window_position
    scaled_rel_position = rel_position.scaled()
    scaled_top_left = (screen - window.scaled()) / 2
    return scaled_rel_position + scaled_top_left
