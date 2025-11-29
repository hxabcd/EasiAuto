"""重写的 QFluentWidgets 组件"""

from typing import List, Union

from PySide6.QtCore import Property, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ColorPickerButton,
    ConfigItem,
    FluentIconBase,
    FluentStyleSheet,
    IconWidget,
    IndicatorPosition,
    LineEdit,
    RangeConfigItem,
    Slider,
    SmoothScrollDelegate,
    SpinBox,
    SwitchButton,
    TableItemDelegate,
    drawIcon,
    isDarkTheme,
    qconfig,
    themeColor,
)


class SettingIconWidget(IconWidget):
    def paintEvent(self, e):
        painter = QPainter(self)

        if not self.isEnabled():
            painter.setOpacity(0.36)

        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        drawIcon(self._icon, painter, self.rect())


class BetterSettingCard(QFrame):
    """
    更好的设置项卡片
    允许设置为列表项（去除边框）
    允许图标为空
    """

    def __init__(self, icon: Union[str, QIcon, FluentIconBase] | None, title, is_item=False, content=None, parent=None):
        """
        注意：对SettingCard套用此类时，仅需修改两项
        1. icon 允许为 None
        2. 增加 is_item 参数并传给 init
        """
        super().__init__(parent=parent)
        self.has_icon = icon is not None
        if self.has_icon:
            self.iconLabel = SettingIconWidget(icon, self)
        self.titleLabel = QLabel(title, self)
        self.contentLabel = QLabel(content or "", self)
        self.hBoxLayout = QHBoxLayout(self)
        self.vBoxLayout = QVBoxLayout()
        self.is_item = is_item

        if not content:
            self.contentLabel.hide()

        self.setFixedHeight(70 if content else 50)
        if self.has_icon:
            self.iconLabel.setFixedSize(16, 16)

        # initialize layout
        self.hBoxLayout.setSpacing(0)
        self.hBoxLayout.setContentsMargins(16, 0, 0, 0)
        self.hBoxLayout.setAlignment(Qt.AlignVCenter)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setAlignment(Qt.AlignVCenter)

        if self.has_icon:
            self.hBoxLayout.addWidget(self.iconLabel, 0, Qt.AlignLeft)
            self.hBoxLayout.addSpacing(16)

        self.hBoxLayout.addLayout(self.vBoxLayout)
        self.vBoxLayout.addWidget(self.titleLabel, 0, Qt.AlignLeft)
        self.vBoxLayout.addWidget(self.contentLabel, 0, Qt.AlignLeft)

        self.hBoxLayout.addSpacing(16)
        self.hBoxLayout.addStretch(1)

        self.contentLabel.setObjectName("contentLabel")
        FluentStyleSheet.SETTING_CARD.apply(self)

    def setTitle(self, title: str):
        """set the title of card"""
        self.titleLabel.setText(title)

    def setContent(self, content: str):
        """set the content of card"""
        self.contentLabel.setText(content)
        self.contentLabel.setVisible(bool(content))

    def setValue(self, value):
        """set the value of config item"""
        pass

    def setIconSize(self, width: int, height: int):
        """set the icon fixed size"""
        self.iconLabel.setFixedSize(width, height)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)

        if isDarkTheme():
            painter.setBrush(QColor(255, 255, 255, 13))
            painter.setPen(QColor(0, 0, 0, 50))
        else:
            painter.setBrush(QColor(255, 255, 255, 170))
            painter.setPen(QColor(0, 0, 0, 19))

        if not self.is_item:
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)


class SwitchSettingCard(BetterSettingCard):
    """开关设置卡"""

    checkedChanged = Signal(bool)

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase] | None,
        title,
        content=None,
        configItem: ConfigItem | None = None,
        is_item: bool = False,
        parent=None,
    ):
        super().__init__(icon, title, is_item, content, parent)
        self.configItem = configItem
        self.switchButton = SwitchButton(self.tr("Off"), self, IndicatorPosition.RIGHT)

        if configItem:
            self.setValue(qconfig.get(configItem))
            configItem.valueChanged.connect(self.setValue)

        # add switch button to layout
        self.hBoxLayout.addWidget(self.switchButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.switchButton.checkedChanged.connect(self.__onCheckedChanged)

    def __onCheckedChanged(self, isChecked: bool):
        self.setValue(isChecked)
        self.checkedChanged.emit(isChecked)

    def setValue(self, isChecked: bool):
        if self.configItem:
            qconfig.set(self.configItem, isChecked)

        self.switchButton.setChecked(isChecked)
        self.switchButton.setText(self.tr("On") if isChecked else self.tr("Off"))

    def setChecked(self, isChecked: bool):
        self.setValue(isChecked)

    def isChecked(self):
        return self.switchButton.isChecked()


class SpinSettingCard(BetterSettingCard):
    """数字输入设置卡"""

    valueChanged = Signal(object)

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase] | None,
        title,
        content=None,
        double: bool = False,
        range: tuple[float, float] | tuple[int, int] | None = None,
        configItem: RangeConfigItem | None = None,
        is_item: bool = False,
        min_width: int | None = None,
        parent=None,
    ):
        """
        增加的设置项：
        double: 使用浮点数
        min_width: 最小宽度
        """
        super().__init__(icon, title, is_item, content, parent)
        self.configItem = configItem
        if double:
            from qfluentwidgets import DoubleSpinBox

            self.spinBox = DoubleSpinBox(self)
        else:
            self.spinBox = SpinBox(self)

        if min_width:
            self.spinBox.setMinimumWidth(min_width)

        if configItem:
            self.setValue(qconfig.get(configItem))
            configItem.valueChanged.connect(self.setValue)
            self.spinBox.setRange(*configItem.range)  # type: ignore

        # add switch button to layout
        self.hBoxLayout.addWidget(self.spinBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.spinBox.valueChanged.connect(self.__onValueChanged)

    def __onValueChanged(self, value: int | float):
        self.setValue(value)
        self.valueChanged.emit(value)

    def setValue(self, value: int | float):
        if self.configItem:
            qconfig.set(self.configItem, value)

        self.spinBox.setValue(value)  # type: ignore


class EditSettingCard(BetterSettingCard):
    """文本输入设置卡"""

    valueChanged = Signal(bool)

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase] | None,
        title,
        content=None,
        configItem: ConfigItem | None = None,
        placeholder_text: str | None = None,
        is_item: bool = False,
        parent=None,
    ):
        super().__init__(icon, title, is_item, content, parent)
        self.configItem = configItem
        self.lineEdit = LineEdit(self)

        if configItem:
            self.setText(qconfig.get(configItem))
            configItem.valueChanged.connect(self.setText)

        if placeholder_text:
            self.lineEdit.setPlaceholderText(placeholder_text)
        elif configItem:
            self.lineEdit.setPlaceholderText(configItem.defaultValue)

        # add switch button to layout
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.lineEdit.textChanged.connect(self.__onTextChanged)

    def __onTextChanged(self, text: str):
        self.setText(text)
        self.valueChanged.emit(text)

    def setText(self, text: str):
        if self.configItem:
            qconfig.set(self.configItem, text)

        self.lineEdit.setText(text)


class ColorSettingCard(BetterSettingCard):
    """颜色设置卡"""

    colorChanged = Signal(QColor)

    def __init__(
        self,
        configItem,
        icon: Union[str, QIcon, FluentIconBase] | None,
        title: str,
        content: str | None = None,
        is_item: bool = False,
        parent=None,
        enableAlpha=False,
    ):
        super().__init__(icon, title, is_item, content, parent)
        self.configItem = configItem
        self.colorPicker = ColorPickerButton(qconfig.get(configItem), title, self, enableAlpha)
        self.hBoxLayout.addWidget(self.colorPicker, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.colorPicker.colorChanged.connect(self.__onColorChanged)
        configItem.valueChanged.connect(self.setValue)

    def __onColorChanged(self, color: QColor):
        qconfig.set(self.configItem, color)
        self.colorChanged.emit(color)

    def setValue(self, color: QColor):
        self.colorPicker.setColor(color)
        qconfig.set(self.configItem, color)


class RangeSettingCard(BetterSettingCard):
    """滑条设置卡"""

    valueChanged = Signal(int)

    def __init__(
        self,
        configItem,
        icon: Union[str, QIcon, FluentIconBase] | None,
        title,
        is_item=False,
        content=None,
        parent=None,
    ):
        super().__init__(icon, title, is_item, content, parent)
        self.configItem = configItem
        self.slider = Slider(Qt.Horizontal, self)
        self.valueLabel = QLabel(self)
        self.slider.setMinimumWidth(268)

        self.slider.setSingleStep(1)
        self.slider.setRange(*configItem.range)
        self.slider.setValue(configItem.value)
        self.valueLabel.setNum(configItem.value)

        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.valueLabel, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(6)
        self.hBoxLayout.addWidget(self.slider, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.valueLabel.setObjectName("valueLabel")
        configItem.valueChanged.connect(self.setValue)
        self.slider.valueChanged.connect(self.__onValueChanged)

    def __onValueChanged(self, value: int):
        """slider value changed slot"""
        self.setValue(value)
        self.valueChanged.emit(value)

    def setValue(self, value):
        qconfig.set(self.configItem, value)
        self.valueLabel.setNum(value)
        self.valueLabel.adjustSize()
        self.slider.setValue(value)


class ListItemDelegate(TableItemDelegate):
    """
    为什么要重写这个？原先的组件加个 Spacing 会直接干掉 Indicator 的绘制
    疑似是 QFW 的 Bug……

    List item delegate
    """

    def __init__(self, parent: QListView):
        super().__init__(parent)  # type: ignore

    def _drawBackground(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.drawRoundedRect(option.rect, 5, 5)

    def _drawIndicator(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        rect = option.rect
        spacing = getattr(self, "spacing", lambda: 0)()  # QListWidget spacing，如果没有就0

        # 计算可绘制高度，扣掉 spacing 的一半在上下
        y = rect.y() + spacing // 2
        h = rect.height() - spacing

        # 根据是否按下行调整上下边距
        ph = round(0.35 * h if getattr(self, "pressedRow", -1) == index.row() else 0.257 * h)

        color = self.darkCheckedColor if isDarkTheme() else self.lightCheckedColor
        painter.setBrush(color if color.isValid() else themeColor())
        painter.setPen(Qt.NoPen)

        # 左边画一条 3px 的竖线
        painter.drawRoundedRect(rect.left(), y + ph, 3, h - 2 * ph, 1.5, 1.5)


class ListBase:
    """
    为什么要重写这个？大抵是沟槽的ListWidget悬浮动画简直一坨，直接砍掉
    基本就是cv一遍，然后注释掉几个绘制阴影的函数……
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.delegate = ListItemDelegate(self)  # type: ignore
        self.scrollDelegate = SmoothScrollDelegate(self)  # type: ignore
        self._isSelectRightClickedRow = False

        FluentStyleSheet.LIST_VIEW.apply(self)  # type: ignore
        self.setItemDelegate(self.delegate)
        self.setMouseTracking(True)

        self.entered.connect(lambda i: self._setHoverRow(i.row()))
        self.pressed.connect(lambda i: self._setPressedRow(i.row()))

    def _setHoverRow(self, row: int):
        """set hovered row"""
        # self.delegate.setHoverRow(row)
        # self.viewport().update()
        pass

    def _setPressedRow(self, row: int):
        """set pressed row"""
        # if self.selectionMode() == QListView.SelectionMode.NoSelection:
        #     return

        # self.delegate.setPressedRow(row)
        # self.viewport().update()
        pass

    def _setSelectedRows(self, indexes: List[QModelIndex]):
        if self.selectionMode() == QListView.SelectionMode.NoSelection:
            return

        self.delegate.setSelectedRows(indexes)
        self.viewport().update()

    def leaveEvent(self, e):
        QListView.leaveEvent(self, e)  # type: ignore
        self._setHoverRow(-1)

    def resizeEvent(self, e):
        QListView.resizeEvent(self, e)  # type: ignore
        self.viewport().update()

    def keyPressEvent(self, e):
        QListView.keyPressEvent(self, e)  # type: ignore
        self.updateSelectedRows()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton or self._isSelectRightClickedRow:
            return QListView.mousePressEvent(self, e)  # type: ignore

        index = self.indexAt(e.pos())
        if index.isValid():
            self._setPressedRow(index.row())

        QWidget.mousePressEvent(self, e)  # type: ignore

    def mouseReleaseEvent(self, e):
        QListView.mouseReleaseEvent(self, e)  # type: ignore
        self.updateSelectedRows()

        if self.indexAt(e.pos()).row() < 0 or e.button() == Qt.RightButton:
            self._setPressedRow(-1)

    def setItemDelegate(self, delegate: ListItemDelegate):
        self.delegate = delegate
        super().setItemDelegate(delegate)

    def clearSelection(self):
        QListView.clearSelection(self)  # type: ignore
        self.updateSelectedRows()

    def setCurrentIndex(self, index: QModelIndex):
        QListView.setCurrentIndex(self, index)  # type: ignore
        self.updateSelectedRows()

    def updateSelectedRows(self):
        self._setSelectedRows(self.selectedIndexes())

    def setCheckedColor(self, light, dark):
        """set the color in checked status

        Parameters
        ----------
        light, dark: str | QColor | Qt.GlobalColor
            color in light/dark theme mode
        """
        self.delegate.setCheckedColor(light, dark)


class ListWidget(ListBase, QListWidget):
    """List widget"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def setCurrentItem(self, item, command=None):
        self.setCurrentRow(self.row(item), command)

    def setCurrentRow(self, row: int, command=None):
        if not command:
            super().setCurrentRow(row)
        else:
            super().setCurrentRow(row, command)

        self.updateSelectedRows()

    def isSelectRightClickedRow(self):
        return self._isSelectRightClickedRow

    def setSelectRightClickedRow(self, isSelect: bool):
        self._isSelectRightClickedRow = isSelect

    selectRightClickedRow = Property(bool, isSelectRightClickedRow, setSelectRightClickedRow)
