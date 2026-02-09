"""重写的 QFluentWidgets 组件"""

from PySide6.QtCore import Property, QModelIndex, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QListView,
    QListWidget,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ExpandLayout,
    FluentStyleSheet,
    IconWidget,
    SmoothScrollDelegate,
    StrongBodyLabel,
    TableItemDelegate,
    drawIcon,
    isDarkTheme,
    themeColor,
)


class SettingIconWidget(IconWidget):
    def paintEvent(self, e):
        painter = QPainter(self)

        if not self.isEnabled():
            painter.setOpacity(0.36)

        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        drawIcon(self._icon, painter, self.rect())



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

    def _setPressedRow(self, row: int):
        """set pressed row"""
        # if self.selectionMode() == QListView.SelectionMode.NoSelection:
        #     return

        # self.delegate.setPressedRow(row)
        # self.viewport().update()

    def _setSelectedRows(self, indexes: list[QModelIndex]):
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
        return None

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


class ListWidget(ListBase, QListWidget):  # type: ignore
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

    def setSelectRightClickedRow(self, isSelect: bool):  # noqa: N803
        self._isSelectRightClickedRow = isSelect

    selectRightClickedRow = Property(bool, isSelectRightClickedRow, setSelectRightClickedRow)


class SettingCardGroup(QWidget):
    """Setting card group"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent=parent)
        # self.titleLabel = QLabel(title, self)
        self.titleLabel = StrongBodyLabel(title, self)
        self.vBoxLayout = QVBoxLayout(self)
        self.cardLayout = ExpandLayout()

        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setAlignment(Qt.AlignTop)
        self.vBoxLayout.setSpacing(0)
        self.cardLayout.setContentsMargins(0, 0, 0, 0)
        self.cardLayout.setSpacing(2)

        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addSpacing(12)
        self.vBoxLayout.addLayout(self.cardLayout, 1)

        FluentStyleSheet.SETTING_CARD_GROUP.apply(self)
        # setFont(self.titleLabel, 20)
        # self.titleLabel.adjustSize()

    def addSettingCard(self, card: QWidget):
        """add setting card to group"""
        card.setParent(self)
        self.cardLayout.addWidget(card)
        self.adjustSize()

    def addSettingCards(self, cards: list[QWidget]):
        """add setting cards to group"""
        for card in cards:
            self.addSettingCard(card)

    def adjustSize(self):
        h = self.cardLayout.heightForWidth(self.width()) + 46
        return self.resize(self.width(), h)
