"""高刷新率的页面切换堆叠控件

qfluentwidgets 的 PopUpAniStackedWidget 由 QAbstractAnimation 驱动，
在本项目环境中实测更新频率仅约 53Hz，动画略显卡顿。本控件改用定时器
自行逐帧插值，帧率跟随主显示器刷新率，呈现更平滑。
"""

from PySide6.QtCore import QEasingCurve, QElapsedTimer, QPoint, QTimer
from PySide6.QtWidgets import QStackedWidget, QWidget

from EasiAuto.core.utils import get_animation_frame_interval


class PopupStackedWidget(QStackedWidget):
    """带浮出动画的堆叠控件（接口与 qfluentwidgets PopUpAniStackedWidget 兼容）

    - 默认进入动画：新页自下方 POPUP_DISTANCE 处浮入原位
    - popOut 模式：当前页向下滑出，新页随后/提前显示
    """

    POPUP_DISTANCE = 76  # 浮出位移（px），与 qfluentwidgets 默认 deltaY 一致
    DURATION = 300  # 动画时长（ms）
    EASING: QEasingCurve.Type = QEasingCurve.Type.OutCubic  # 缓动曲线

    def __init__(self, parent=None):
        super().__init__(parent)
        self._animating = False
        self._is_animation_enabled = True
        self._widget: QWidget | None = None
        self._start_pos = QPoint()
        self._pop_out = False
        self._target_index: int | None = None
        self._duration = self.DURATION
        self._easing = self.EASING
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(self._frame_interval())
        self._timer.timeout.connect(self._on_tick)

    @staticmethod
    def _frame_interval() -> int:
        """按主显示器刷新率计算动画帧间隔（毫秒）"""
        return get_animation_frame_interval()

    @property
    def is_animating(self) -> bool:
        """是否正在播放切换动画"""
        return self._animating

    def setAnimationEnabled(self, is_enabled: bool) -> None:
        """设置是否启用切换动画"""
        self._is_animation_enabled = is_enabled

    def isAnimationEnabled(self) -> bool:
        """是否启用切换动画"""
        return self._is_animation_enabled

    def setCurrentWidget(
        self,
        widget,
        need_pop_out: bool = False,
        show_next_widget_directly: bool = True,
        duration: int | None = None,
        easing_curve: QEasingCurve.Type | None = None,
    ):
        self.setCurrentIndex(self.indexOf(widget), need_pop_out, show_next_widget_directly, duration, easing_curve)

    def setCurrentIndex(
        self,
        index: int,
        need_pop_out: bool = False,
        show_next_widget_directly: bool = True,
        duration: int | None = None,
        easing_curve: QEasingCurve.Type | None = None,
    ):
        if index == self.currentIndex():
            return
        if self._animating:
            # 打断进行中的动画并让旧页归位
            self._finish()

        if not self._is_animation_enabled:
            super().setCurrentIndex(index)
            return

        if need_pop_out:
            current = self.widget(self.currentIndex())
            target = self.widget(index)
            if current is None or target is None:
                super().setCurrentIndex(index)
                return
            # 当前页向下滑出，可提前显示新页
            self._widget = current
            self._start_pos = current.pos()
            self._pop_out = True
            target.setVisible(show_next_widget_directly)
        else:
            target = self.widget(index)
            if target is None:
                super().setCurrentIndex(index)
                return
            # 立即切换并让新页自下方浮入
            super().setCurrentIndex(index)
            self._widget = target
            self._start_pos = target.pos()
            self._pop_out = False

        self._target_index = index
        self._duration = duration or self.DURATION
        self._easing = easing_curve or self.EASING
        self._animating = True
        self._widget.move(self._start_pos.x(), self._start_pos.y() + self.POPUP_DISTANCE)
        self._elapsed.restart()
        self._timer.start()

    def _on_tick(self) -> None:
        widget = self._widget
        if widget is None:
            self._finish()
            return
        progress = min(self._elapsed.elapsed() / self._duration, 1.0)
        eased = QEasingCurve(self._easing).valueForProgress(progress)
        delta = round(self.POPUP_DISTANCE * eased)
        y = self._start_pos.y() + (delta if self._pop_out else self.POPUP_DISTANCE - delta)
        if progress >= 1.0:
            widget.move(self._start_pos.x(), self._start_pos.y())
            self._finish()
        else:
            widget.move(self._start_pos.x(), y)

    def _finish(self) -> None:
        self._timer.stop()
        if self._widget is not None:
            self._widget.move(self._start_pos.x(), self._start_pos.y())
        self._widget = None
        if self._target_index is not None and self.currentIndex() != self._target_index:
            # popOut 模式下此前尚未真正切换页面
            super().setCurrentIndex(self._target_index)
        self._target_index = None
        self._animating = False
