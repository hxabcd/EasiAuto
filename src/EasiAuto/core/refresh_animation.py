"""QPropertyAnimation 的高刷新率替代驱动

Qt6 的 QAbstractAnimation 由统一定时器驱动，本项目环境中实测更新频率
仅约 53Hz。本驱动改用高频 QTimer 按主显示器刷新率逐帧插值，用于替换
依赖库中因 QPropertyAnimation 而卡顿的动画。
"""

from __future__ import annotations

from contextlib import suppress

from shiboken6 import isValid

from PySide6.QtCore import (
    Property,
    QAbstractAnimation,
    QEasingCurve,
    QElapsedTimer,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    QSizeF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor
from qfluentwidgets.common.animation import (
    FluentAnimationProperObject,
    FluentAnimationProperty,
    FluentAnimationSpeed,
    FluentAnimationType,
)

from EasiAuto.core.utils import get_animation_frame_interval


def _same_category(a, b) -> bool:
    """判断起点/终点是否同一类型语义（int/float 视为同类）"""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return True
    return type(a) is type(b)


def _interp(start, end, t):
    """按类型插值动画值（t ∈ [0, 1]）"""
    # 起点/终点类型不一致时直接跳到终值，避免属性访问崩溃（与 Qt 语义近似）
    if not _same_category(start, end):
        return end
    if isinstance(end, QColor):
        return QColor(
            round(start.red() + (end.red() - start.red()) * t),
            round(start.green() + (end.green() - start.green()) * t),
            round(start.blue() + (end.blue() - start.blue()) * t),
            round(start.alpha() + (end.alpha() - start.alpha()) * t),
        )
    if isinstance(end, (QPointF, QPoint)):
        x = start.x() + (end.x() - start.x()) * t
        y = start.y() + (end.y() - start.y()) * t
        return QPoint(round(x), round(y)) if isinstance(end, QPoint) else QPointF(x, y)
    if isinstance(end, QRectF):
        return QRectF(
            start.x() + (end.x() - start.x()) * t,
            start.y() + (end.y() - start.y()) * t,
            start.width() + (end.width() - start.width()) * t,
            start.height() + (end.height() - start.height()) * t,
        )
    if isinstance(end, QRect):
        return QRect(
            round(start.x() + (end.x() - start.x()) * t),
            round(start.y() + (end.y() - start.y()) * t),
            round(start.width() + (end.width() - start.width()) * t),
            round(start.height() + (end.height() - start.height()) * t),
        )
    if isinstance(end, (QSizeF, QSize)):
        w = start.width() + (end.width() - start.width()) * t
        h = start.height() + (end.height() - start.height()) * t
        return QSize(round(w), round(h)) if isinstance(end, QSize) else QSizeF(w, h)
    if isinstance(end, (int, float)):
        return start + (end - start) * t
    # 未知类型退化为直接跳转终值，避免崩溃
    return end


class RefreshDrivenAnimation(QObject):
    """按主显示器刷新率逐帧插值的属性动画（QPropertyAnimation 兼容子集）

    支持数值、颜色、坐标、矩形、尺寸等常见属性类型；提供
    start/stop/state、setStartValue/setEndValue/setDuration/setEasingCurve/
    setTargetObject/setPropertyName 及 valueChanged/finished，可直接替换
    QPropertyAnimation。
    """

    valueChanged = Signal(object)
    finished = Signal()

    # 兼容 QPropertyAnimation.Running / Stopped 这类类属性比较
    Running = QAbstractAnimation.State.Running
    Stopped = QAbstractAnimation.State.Stopped
    Paused = QAbstractAnimation.State.Paused

    def __init__(self, target: QObject | None = None, property_name: bytes | None = None, parent=None) -> None:
        super().__init__(parent)
        self._target = target
        self._property_name = property_name.decode() if property_name else ""
        self._start = 0.0
        self._start_set = False  # 是否显式设置过起点（未设置时 start() 取属性当前值）
        self._end = 0.0
        self._current = None
        self._duration = 200
        self._easing: QEasingCurve = QEasingCurve(QEasingCurve.Type.Linear)
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(get_animation_frame_interval())
        self._timer.timeout.connect(self._tick)

    def setTargetObject(self, target: QObject) -> None:
        """设置动画目标对象"""
        self._target = target

    def setPropertyName(self, name: bytes) -> None:
        """设置目标属性名"""
        self._property_name = name.decode()

    def setStartValue(self, value) -> None:
        """设置动画起始值"""
        self._start = value
        self._start_set = True

    def setEndValue(self, value) -> None:
        """设置动画结束值"""
        self._end = value

    def startValue(self):
        return self._start

    def endValue(self):
        return self._end

    def currentValue(self):
        return self._current

    def setCurrentTime(self, msecs: int) -> None:
        """直接跳转到指定时刻（兼容 seek 用法）"""
        progress = min(msecs / self._duration, 1.0)
        self._evaluate(self._easing.valueForProgress(progress))

    def setDuration(self, msecs: int) -> None:
        """设置动画时长（毫秒）"""
        self._duration = max(msecs, 1)

    def duration(self) -> int:
        return self._duration

    def totalDuration(self) -> int:
        return self._duration

    def setEasingCurve(self, curve) -> None:
        """设置缓动曲线（接受 QEasingCurve.Type 或 QEasingCurve 实例）"""
        self._easing = curve if isinstance(curve, QEasingCurve) else QEasingCurve(curve)

    def easingCurve(self) -> QEasingCurve:
        return self._easing

    def _target_alive(self) -> bool:
        """目标对象及其 C++ 实例是否仍然有效"""
        return self._target is None or isValid(self._target)

    def start(self) -> None:
        """启动动画

        与 QPropertyAnimation 一致：未显式设置起点时，取目标属性当前值。
        """
        if not self._start_set:
            self._start = self.value()
        self._elapsed.restart()
        self._timer.start()

    def stop(self) -> None:
        """停止动画"""
        self._timer.stop()

    def state(self) -> QAbstractAnimation.State:
        return QAbstractAnimation.State.Running if self._timer.isActive() else QAbstractAnimation.State.Stopped

    def value(self):
        """读取目标当前值（配合 ProperObject 与 FluentAnimation 使用）"""
        target = self._target
        if target is None or not isValid(target):
            return self._current
        getter = getattr(target, "getValue", None)
        if callable(getter):
            return getter()
        if self._property_name:
            try:
                return target.property(self._property_name)
            except Exception:
                pass
        return self._current

    def setValue(self, value) -> None:
        """直接设置目标值"""
        self._set_target_property(value)
        self._current = value

    def _evaluate(self, eased: float) -> None:
        value = _interp(self._start, self._end, eased)
        self._set_target_property(value)
        self._current = value
        self.valueChanged.emit(value)

    def _set_target_property(self, value) -> None:
        if self._target is None or not self._property_name or not isValid(self._target):
            return
        try:
            self._target.setProperty(self._property_name, value)
        except TypeError:
            # 整型属性不接受浮点赋值时退化为整数
            self._target.setProperty(self._property_name, int(round(value)))

    def _tick(self) -> None:
        if not self._target_alive():
            # 目标已销毁（如控件关闭时移除透明度效果），停止动画并收尾
            self._timer.stop()
            self.finished.emit()
            return
        progress = min(self._elapsed.elapsed() / self._duration, 1.0)
        self._evaluate(self._easing.valueForProgress(progress))
        if progress >= 1.0:
            self._timer.stop()
            self.finished.emit()


class RefreshParallelGroup(QObject):
    """QParallelAnimationGroup 的高刷新率替代

    成员动画并行执行（各自独立驱动），全部结束后发出 finished。
    支持 add/insert/remove/clear/start/stop 与成员查询接口。
    """

    finished = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._anims: list[RefreshDrivenAnimation] = []
        self._connected: list[RefreshDrivenAnimation] = []
        self._pending = 0

    def addAnimation(self, ani: RefreshDrivenAnimation) -> None:
        self._anims.append(ani)

    def insertAnimation(self, index: int, ani: RefreshDrivenAnimation) -> None:
        self._anims.insert(index, ani)

    def removeAnimation(self, ani: RefreshDrivenAnimation) -> None:
        if ani in self._anims:
            self._anims.remove(ani)
            self._disconnect(ani)

    def clear(self) -> None:
        for ani in self._anims:
            self._disconnect(ani)
        self._anims.clear()

    def animationCount(self) -> int:
        return len(self._anims)

    def animation(self, index: int) -> RefreshDrivenAnimation:
        return self._anims[index]

    def indexOfAnimation(self, ani: RefreshDrivenAnimation) -> int:
        return self._anims.index(ani) if ani in self._anims else -1

    def start(self) -> None:
        self.stop()
        self._pending = len(self._anims)
        for ani in self._anims:
            if ani not in self._connected:
                ani.finished.connect(self._on_finished)
                self._connected.append(ani)
            ani.start()

    def stop(self) -> None:
        for ani in self._anims:
            ani.stop()

    def _disconnect(self, ani: RefreshDrivenAnimation) -> None:
        if ani not in self._connected:
            return
        with suppress(Exception):
            ani.finished.disconnect(self._on_finished)
        self._connected.remove(ani)

    def _on_finished(self) -> None:
        self._pending -= 1
        if self._pending <= 0:
            self.finished.emit()


def _bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    """构造三次贝塞尔缓动曲线"""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1, 1))
    return curve


def _lerp_point(start: QPointF, end: QPointF, t: float) -> QPointF:
    """按比例插值二维坐标"""
    return QPointF(start.x() + (end.x() - start.x()) * t, start.y() + (end.y() - start.y()) * t)


class RefreshScaleSlideAnimation(QObject):
    """qfluentwidgets ScaleSlideAnimation 的高刷新率替代

    公开接口与语义保持一致（分段贝塞尔滑入、crossfade 两种模式，总时长
    600ms），改用定时器按主显示器刷新率逐帧驱动，替代 QPropertyAnimation
    约 53Hz 的帧率瓶颈。用于 Pivot 标签指示器与侧边导航指示器。
    """

    valueChanged = Signal(QRectF)
    finished = Signal()

    CURVE_1 = _bezier(0.9, 0.1, 1, 0.2)  # 前 1/3 段
    CURVE_2 = _bezier(0.1, 0.9, 0.2, 1.0)  # 后 2/3 段
    DURATION = 600

    def __init__(self, parent=None, orient=Qt.Orientation.Horizontal):
        super().__init__(parent)
        self.orient = orient
        self._geometry = QRectF(0, 0, 16, 3) if self.isHorizontal() else QRectF(0, 0, 3, 16)
        self._mode: str | None = None
        self._seg = {}
        self._cross = {}
        self._end_rect = QRectF()
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(get_animation_frame_interval())
        self._timer.timeout.connect(self._tick)

    # ---------- 与 ScaleSlideAnimation 一致的公开接口 ----------

    def startAnimation(self, end_rect: QRectF, use_cross_fade: bool = False) -> None:
        self.stopAnimation()
        start_rect = QRectF(self._geometry)

        if self.isHorizontal():
            same_level = abs(start_rect.y() - end_rect.y()) < 1
            dim = start_rect.width()
            start = start_rect.x()
            end = end_rect.x()
        else:
            same_level = abs(start_rect.x() - end_rect.x()) < 1
            dim = start_rect.height()
            start = start_rect.y()
            end = end_rect.y()

        if same_level and not use_cross_fade:
            self._set_slide(start_rect, end_rect, start, end, dim)
        else:
            self._set_cross(start_rect, end_rect)

        self._elapsed.restart()
        self._timer.start()

    def stopAnimation(self) -> None:
        self._timer.stop()

    def stop(self) -> None:
        self.stopAnimation()

    def setValue(self, rect: QRectF) -> None:
        """直接设置几何（不触发动画）"""
        self.setGeometry(rect)

    def isHorizontal(self) -> bool:
        return self.orient == Qt.Orientation.Horizontal

    def getGeometry(self) -> QRectF:
        return self._geometry

    def setGeometry(self, rect: QRectF) -> None:
        self._geometry = rect

    geometry = Property(QRectF, getGeometry, setGeometry)

    # ---------- 模式初始化 ----------

    def _set_slide(self, start_rect: QRectF, end_rect: QRectF, from_: float, to: float, dimension: float) -> None:
        """WinUI 3 拉伸式滑入：前段拉长覆盖两项目，后段收拢到位"""
        self._mode = "slide"
        self._end_rect = end_rect
        mid_length = abs(to - from_) + dimension
        start_pos = start_rect.topLeft()
        end_pos = end_rect.topLeft()
        if to > from_:
            # 0->1/3: B 移至 M（拉长）；1/3->1: A 移至 A'
            self._seg = {
                "pos1": (start_pos, start_pos),
                "pos2": (start_pos, end_pos),
                "len": (dimension, mid_length, dimension),
            }
        else:
            # 0->1/3: A 移至 M（拉长）；1/3->1: B 移至 B'
            self._seg = {
                "pos1": (start_pos, end_pos),
                "pos2": (end_pos, end_pos),
                "len": (dimension, mid_length, dimension),
            }

    def _set_cross(self, start_rect: QRectF, end_rect: QRectF) -> None:
        """crossfade：从目标位置边缘生长"""
        self._mode = "cross"
        self._end_rect = end_rect
        self.setGeometry(end_rect)
        is_next_below = end_rect.y() > start_rect.y() if not self.isHorizontal() else end_rect.x() > start_rect.x()

        if self.isHorizontal():
            dim = end_rect.width()
            start_geo = QRectF(end_rect.x() + (0 if is_next_below else dim), end_rect.y(), 0, end_rect.height())
        else:
            dim = end_rect.height()
            start_geo = QRectF(end_rect.x(), end_rect.y() + (0 if is_next_below else dim), end_rect.width(), 0)

        self.setGeometry(start_geo)
        self._cross = {"pos1": start_geo.topLeft(), "pos2": end_rect.topLeft(), "dim": dim}

    # ---------- 逐帧驱动 ----------

    def _tick(self) -> None:
        progress = min(self._elapsed.elapsed() / self.DURATION, 1.0)
        if self._mode == "slide":
            self._apply_slide(progress)
        elif self._mode == "cross":
            self._apply_cross(progress)
        if progress >= 1.0:
            self.setGeometry(self._end_rect)
            self._timer.stop()
            self.finished.emit()

    def _apply_slide(self, t: float) -> None:
        seg = self._seg
        if t < 1 / 3:
            u = t * 3
            eased = self.CURVE_1.valueForProgress(u)
            pos1, pos2 = seg["pos1"]
            len1, mid, len2 = seg["len"]
            self.setPos(_lerp_point(pos1, pos2, eased))
            self.setLength(len1 + (mid - len1) * eased)
        else:
            u = (t - 1 / 3) * 1.5
            eased = self.CURVE_2.valueForProgress(u)
            pos1, pos2 = seg["pos2"]
            len1, mid, len2 = seg["len"]
            self.setPos(_lerp_point(pos1, pos2, eased))
            self.setLength(mid + (len2 - mid) * eased)

    def _apply_cross(self, t: float) -> None:
        eased = QEasingCurve(QEasingCurve.Type.OutQuint).valueForProgress(t)
        cross = self._cross
        self.setPos(_lerp_point(cross["pos1"], cross["pos2"], eased))
        self.setLength(cross["dim"] * eased)

    # ---------- 属性写入（同时发出信号） ----------

    def setPos(self, pos: QPointF) -> None:
        self._geometry.moveTopLeft(pos)
        self.valueChanged.emit(self.geometry)

    def setLength(self, length: float) -> None:
        if self.isHorizontal():
            self._geometry.setWidth(length)
        else:
            self._geometry.setHeight(length)
        self.valueChanged.emit(self.geometry)


class RefreshFluentAnimation(RefreshDrivenAnimation):
    """qfluentwidgets FluentAnimation 的高刷新率替代

    保留 setSpeed/startAnimation/value/setValue 与 create 注册表工厂，
    供菜单、浮出层、分段控件等 FADE_IN_OUT/POINT_TO_POINT 类动画使用。
    """

    animations = {}

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setSpeed(FluentAnimationSpeed.FAST)
        self.setEasingCurve(self.curve())

    @classmethod
    def createBezierCurve(cls, x1, y1, x2, y2):
        return _bezier(x1, y1, x2, y2)

    @classmethod
    def curve(cls):
        return cls.createBezierCurve(0, 0, 1, 1)

    def setSpeed(self, speed: FluentAnimationSpeed) -> None:
        """按速度档位设置动画时长"""
        self.setDuration(self.speedToDuration(speed))

    def speedToDuration(self, speed: FluentAnimationSpeed) -> int:
        return 100

    def startAnimation(self, end_value, start_value=None) -> None:
        """从当前值（或指定值）动画到目标值"""
        self.stop()
        self.setStartValue(start_value if start_value is not None else self.value())
        self.setEndValue(end_value)
        self.start()

    @classmethod
    def register(cls, name):
        """注册动画类型"""

        def wrapper(manager):
            if name not in cls.animations:
                cls.animations[name] = manager
            return manager

        return wrapper

    @classmethod
    def create(
        cls,
        ani_type: FluentAnimationType,
        property_type: FluentAnimationProperty,
        speed: FluentAnimationSpeed = FluentAnimationSpeed.FAST,
        value=None,
        parent=None,
    ):
        """创建指定类型与属性的动画实例（与 FluentAnimation.create 一致）"""
        if ani_type not in cls.animations:
            raise ValueError(f"`{ani_type}` has not been registered.")

        obj = FluentAnimationProperObject.create(property_type, parent)
        ani = cls.animations[ani_type](parent)

        ani.setSpeed(speed)
        ani.setTargetObject(obj)
        ani.setPropertyName(property_type.value.encode())

        if value is not None:
            ani.setValue(value)

        return ani


@RefreshFluentAnimation.register(FluentAnimationType.FAST_INVOKE)
class RefreshFastInvokeAnimation(RefreshFluentAnimation):
    """快速唤起动画"""

    @classmethod
    def curve(cls):
        return cls.createBezierCurve(0, 0, 0, 1)

    def speedToDuration(self, speed: FluentAnimationSpeed) -> int:
        if speed == FluentAnimationSpeed.FAST:
            return 187
        if speed == FluentAnimationSpeed.MEDIUM:
            return 333
        return 500


@RefreshFluentAnimation.register(FluentAnimationType.STRONG_INVOKE)
class RefreshStrongInvokeAnimation(RefreshFluentAnimation):
    """强唤起动画"""

    @classmethod
    def curve(cls):
        return cls.createBezierCurve(0.13, 1.62, 0, 0.92)

    def speedToDuration(self, speed: FluentAnimationSpeed) -> int:
        return 667


@RefreshFluentAnimation.register(FluentAnimationType.FAST_DISMISS)
class RefreshFastDismissAnimation(RefreshFastInvokeAnimation):
    """快速消失动画"""


@RefreshFluentAnimation.register(FluentAnimationType.SOFT_DISMISS)
class RefreshSoftDismissAnimation(RefreshFluentAnimation):
    """柔滑消失动画"""

    @classmethod
    def curve(cls):
        return cls.createBezierCurve(1, 0, 1, 1)

    def speedToDuration(self, speed: FluentAnimationSpeed) -> int:
        return 167


@RefreshFluentAnimation.register(FluentAnimationType.POINT_TO_POINT)
class RefreshPointToPointAnimation(RefreshFastDismissAnimation):
    """点到点动画"""

    @classmethod
    def curve(cls):
        return cls.createBezierCurve(0.55, 0.55, 0, 1)


@RefreshFluentAnimation.register(FluentAnimationType.FADE_IN_OUT)
class RefreshFadeInOutAnimation(RefreshFluentAnimation):
    """淡入淡出动画"""

    def speedToDuration(self, speed: FluentAnimationSpeed) -> int:
        return 83


def make_icon_slide_animation(animation_class):
    """构造 navigation_bar.IconSlideAnimation 的高刷新率替代"""

    class IconSlideAnimation(animation_class):
        def __init__(self, parent=None):
            super().__init__(parent=parent)
            self._offset = 0.0
            self.maxOffset = 6
            self.setTargetObject(self)
            self.setPropertyName(b"offset")

        def getOffset(self):
            return self._offset

        def setOffset(self, value):
            self._offset = value
            self.parent().update()

        def slideDown(self):
            self.setEndValue(self.maxOffset)
            self.setDuration(100)
            self.start()

        def slideUp(self):
            self.setEndValue(0)
            self.setDuration(100)
            self.start()

        offset = Property(float, getOffset, setOffset)

    return IconSlideAnimation
