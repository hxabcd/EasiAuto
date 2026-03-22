"""重写的 QFluentWidgets 组件"""


from PySide6.QtCore import Property, QModelIndex, Qt
from PySide6.QtGui import QColor, QPainter
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
    PushButton,
    SmoothScrollDelegate,
    StrongBodyLabel,
    TableItemDelegate,
    ThemeColor,
    drawIcon,
    isDarkTheme,
    themeColor,
)

from EasiAuto.view.utils import set_tooltip


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
        super().__init__(parent)

    def _drawBackground(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        if index.row() in self.selectedRows:
            return
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
        self.delegate = ListItemDelegate(self)
        self.scrollDelegate = SmoothScrollDelegate(self)
        self._isSelectRightClickedRow = False

        FluentStyleSheet.LIST_VIEW.apply(self)
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
        QListView.leaveEvent(self, e)
        self._setHoverRow(-1)

    def resizeEvent(self, e):
        QListView.resizeEvent(self, e)
        self.viewport().update()

    def keyPressEvent(self, e):
        QListView.keyPressEvent(self, e)
        self.updateSelectedRows()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton or self._isSelectRightClickedRow:
            return QListView.mousePressEvent(self, e)

        index = self.indexAt(e.pos())
        if index.isValid():
            self._setPressedRow(index.row())

        QWidget.mousePressEvent(self, e)
        return None

    def mouseReleaseEvent(self, e):
        QListView.mouseReleaseEvent(self, e)
        self.updateSelectedRows()

        if self.indexAt(e.pos()).row() < 0 or e.button() == Qt.RightButton:
            self._setPressedRow(-1)

    def setItemDelegate(self, delegate: ListItemDelegate):
        self.delegate = delegate
        super().setItemDelegate(delegate)

    def clearSelection(self):
        QListView.clearSelection(self)
        self.updateSelectedRows()

    def setCurrentIndex(self, index: QModelIndex):
        QListView.setCurrentIndex(self, index)
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


class PillButtonBase:
    """Pill button base class 仅复制粘贴"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)
        isDark = isDarkTheme()

        if not self.isChecked():
            rect = self.rect().adjusted(1, 1, -1, -1)
            borderColor = QColor(255, 255, 255, 18) if isDark else QColor(0, 0, 0, 15)

            if not self.isEnabled():
                bgColor = QColor(255, 255, 255, 11) if isDark else QColor(249, 249, 249, 75)
            elif self.isPressed or self.isHover:
                bgColor = QColor(255, 255, 255, 21) if isDark else QColor(249, 249, 249, 128)
            else:
                bgColor = QColor(255, 255, 255, 15) if isDark else QColor(243, 243, 243, 194)

        else:
            if not self.isEnabled():
                bgColor = QColor(255, 255, 255, 40) if isDark else QColor(0, 0, 0, 55)
            elif self.isPressed:
                bgColor = ThemeColor.DARK_2.color() if isDark else ThemeColor.LIGHT_3.color()
            elif self.isHover:
                bgColor = ThemeColor.DARK_1.color() if isDark else ThemeColor.LIGHT_1.color()
            else:
                bgColor = themeColor()

            borderColor = Qt.transparent
            rect = self.rect()

        painter.setPen(borderColor)
        painter.setBrush(bgColor)

        r = rect.height() / 2
        painter.drawRoundedRect(rect, r, r)


class PillPushButton(PushButton, PillButtonBase):
    """Pill push button (非切换按钮)

    Constructors
    ------------
    * PillPushButton(`parent`: QWidget = None)
    * PillPushButton(`text`: str, `parent`: QWidget = None,
                     `icon`: QIcon | str | FluentIconBase = None)
    * PillPushButton(`icon`: QIcon | FluentIcon, `text`: str, `parent`: QWidget = None)
    """

    def paintEvent(self, e):
        PillButtonBase.paintEvent(self, e)
        PushButton.paintEvent(self, e)


class PillOverflowBar(QWidget):
    """Pill 标签栏（首尾固定，中间尽量显示，溢出使用省略按钮）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags: list[PillPushButton] = []
        self._last_widget: QWidget | None = None
        self._spacing = 6

        self.ellipsis_button = PillPushButton("...", self)
        self.ellipsis_button.hide()

    def setSpacing(self, spacing: int):
        self._spacing = max(0, spacing)
        self._update_geometry()

    def spacing(self) -> int:
        return self._spacing

    def setLastWidget(self, widget: QWidget):
        self._last_widget = widget
        widget.setParent(self)
        widget.show()
        self._update_geometry()

    def setTags(self, tags: list[str]):
        for tag in self._tags:
            tag.hide()
            tag.deleteLater()

        self._tags.clear()

        for text in tags:
            button = PillPushButton(text, self)
            button.show()
            self._tags.append(button)

        self._update_geometry()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_geometry()

    def _update_geometry(self):
        m = self.contentsMargins()
        available_width = max(0, self.width() - m.left() - m.right())
        spacing = self._spacing

        first = self._tags[0] if self._tags else None
        middle = self._tags[1:] if len(self._tags) > 1 else []
        last = self._last_widget

        for btn in self._tags:
            btn.hide()
        if last:
            last.hide()
        self.ellipsis_button.hide()

        first_w = first.sizeHint().width() if first else 0
        last_w = last.sizeHint().width() if last else 0
        ellipsis_w = self.ellipsis_button.sizeHint().width()

        used = 0
        if first:
            used += first_w
        if last:
            used += last_w
        if first and last:
            used += spacing

        visible_middle: list[PillPushButton] = []
        hidden_middle: list[PillPushButton] = []

        for i, btn in enumerate(middle):
            need = btn.sizeHint().width() + spacing
            has_more_after = i < len(middle) - 1
            reserve = ellipsis_w + spacing if has_more_after else 0

            if used + need + reserve <= available_width:
                visible_middle.append(btn)
                used += need
            else:
                hidden_middle = middle[i:]
                break

        order: list[QWidget] = []
        if first:
            order.append(first)
        order.extend(visible_middle)
        if hidden_middle:
            hidden_titles = [btn.text() for btn in hidden_middle]
            set_tooltip(self.ellipsis_button, ", ".join(hidden_titles))
            order.append(self.ellipsis_button)
        if last:
            order.append(last)

        x = m.left()
        max_h = 0
        for i, widget in enumerate(order):
            hint = widget.sizeHint()
            y = m.top()
            widget.move(x, y)
            widget.show()
            x += hint.width()
            if i < len(order) - 1:
                x += spacing
            max_h = max(max_h, hint.height())

        if max_h == 0:
            max_h = self.ellipsis_button.sizeHint().height()
        self.setMinimumHeight(m.top() + max_h + m.bottom())


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
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
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
