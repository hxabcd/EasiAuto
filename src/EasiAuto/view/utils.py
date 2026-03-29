from enum import Enum
from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import ExpandGroupSettingCard, FluentIconBase, SwitchButton, ToolTipFilter
from qfluentwidgets.common.config import Theme

from EasiAuto.common.utils import get_resource

if TYPE_CHECKING:
    from EasiAuto.view.main_window import MainWindow


class Icons(FluentIconBase, Enum):
    """一些自定义图标"""

    ClassIsland = "ClassIsland.svg"

    def path(self, theme=Theme.AUTO) -> str:
        return get_resource(f"icons/{self.value}")


def set_enable_by(widgets: list[QWidget] | QWidget, switch: SwitchButton, reverse: bool = False):
    """通过开关启用组件"""
    widgets = [widgets] if isinstance(widgets, QWidget) else widgets

    def handle_check_change(checked: bool):
        for widget in widgets:
            is_enabled = checked if not reverse else not checked
            widget.setEnabled(is_enabled)
            if not is_enabled and isinstance(widget, ExpandGroupSettingCard):
                widget.setExpand(False)

    handle_check_change(switch.isChecked())
    switch.checkedChanged.connect(handle_check_change)

def set_tooltip(widget: QWidget, tooltip: str):
    """使用更 Fluent 的方式设置 ToolTip"""
    widget.setToolTip(tooltip)
    widget.installEventFilter(ToolTipFilter(widget))


def get_main_window() -> "MainWindow":
    """通过 objectName 获取主窗口实例"""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication 尚未初始化")

    for widget in app.topLevelWidgets():
        if widget.objectName() == "MainWindow":
            return widget  # type: ignore[return-value]

    raise RuntimeError("未找到主窗口")


def get_main_container() -> QWidget:
    """获取主窗口容器"""
    main_window = get_main_window()
    return main_window.stackedWidget


def get_app() -> QApplication:
    """获取 QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication 尚未初始化")
    return cast(QApplication, app)
