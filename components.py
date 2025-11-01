from typing import Union

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
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
    SpinBox,
    SwitchButton,
    drawIcon,
    isDarkTheme,
    qconfig,
)

from config import BannerConfig
from utils import get_resource


class WarningPopupWindow(QMessageBox):
    """运行前的警告弹窗"""

    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.WindowStaysOnTopHint)  # 窗口置顶
        self.setIcon(QMessageBox.Warning)
        self.setWindowTitle("EasiAuto")
        self.setWindowIcon(QIcon(get_resource("easiauto.ico")))
        self.setText("<span style='font-size: 20px; font-weight: bold;'>即将运行希沃白板自动登录</span>")
        self.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        self.button(QMessageBox.Ok).setText("立即执行")
        self.button(QMessageBox.Cancel).setText("取消")

    def countdown(self, timeout: int = 15):
        # 设置倒计时
        if timeout <= 0:
            timeout = 15

        # 更新倒计时文本
        def update_text():
            nonlocal timeout
            if timeout > 0:
                self.setInformativeText(f"将在 {timeout} 秒后继续执行")
                timeout -= 1
            else:
                self.button(QMessageBox.Ok).click()
                timer.stop()

        update_text()

        # 计时器
        timer = QTimer()
        timer.timeout.connect(update_text)
        timer.setInterval(1000)
        timer.start()

        result = self.exec()

        timer.stop()

        if result == QMessageBox.Cancel:
            return 0  # 手动取消
        return 1  # 确认/超时继续


class WarningBanner(QWidget):
    """顶部警示横幅"""

    def __init__(self, config: BannerConfig):
        super().__init__()
        self.config = config

        self.setFixedHeight(140)  # 横幅高度
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # 置顶、无边框、点击穿透
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)

        # 滚动文字
        self.text = self.config.Text
        self.text_x = 0
        self.text_speed = self.config.TextSpeed
        self.text_y_offset = self.config.YOffset

        font = QFont(["HarmonyOS Sans SC", "Microsoft YaHei UI", "sans-serif"], pointSize=36, weight=QFont.Bold)
        self.text_font = font

        # 生成斜纹
        self.stripe = QPixmap(40, 32)
        self.stripe.fill(Qt.transparent)
        painter = QPainter(self.stripe)
        painter.setBrush(QColor(self.config.FgColor))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon([QPoint(0, 32), QPoint(16, 0), QPoint(32, 0), QPoint(16, 32)])
        painter.end()

        self.offset = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(1000 // self.config.Fps)

    def animate(self):
        # 条纹滚动
        self.offset = (self.offset + 1) % self.stripe.width()

        # 文字滚动
        self.text_x -= self.text_speed
        # 文字总长度
        total_text_width = QFontMetrics(self.text_font).horizontalAdvance(self.text)
        if self.text_x < -total_text_width:
            self.text_x += total_text_width  # 循环滚动，不跳空
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)

        # 背景颜色
        painter.fillRect(self.rect(), QColor(self.config.BgColor))
        # 顶部条纹
        y = 0
        x = -self.offset
        while x < self.width():
            painter.drawPixmap(x, y, self.stripe)
            x += self.stripe.width()

        # 分割线（条纹下边缘）
        painter.setPen(QPen(QColor(self.config.FgColor), 4))
        painter.drawLine(0, self.stripe.height(), self.width(), self.stripe.height())

        # 底部条纹
        y = self.height() - self.stripe.height()
        x = -self.offset
        while x < self.width():
            painter.drawPixmap(x, y, self.stripe)
            x += self.stripe.width()

        # 分割线（条纹上边缘）
        painter.drawLine(0, y, self.width(), y)

        # 滚动文字（循环绘制多份）
        painter.setFont(self.text_font)
        painter.setPen(QColor(self.config.TextColor))
        text_width = painter.fontMetrics().horizontalAdvance(self.text)
        x = self.text_x
        while x < self.width():
            painter.drawText(x, int(self.height() / 2 + self.text_y_offset), self.text)
            x += text_width


class SettingIconWidget(IconWidget):
    def paintEvent(self, e):
        painter = QPainter(self)

        if not self.isEnabled():
            painter.setOpacity(0.36)

        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        drawIcon(self._icon, painter, self.rect())


class BetterSettingCard(QFrame):
    """Setting card"""

    def __init__(self, icon: Union[str, QIcon, FluentIconBase] | None, title, is_item=False, content=None, parent=None):
        """
        Parameters
        ----------
        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        parent: QWidget
            parent widget
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
        if not is_item:
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
    """Setting card with switch button"""

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
        """
        Parameters
        ----------
        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        configItem: ConfigItem
            configuration item operated by the card

        parent: QWidget
            parent widget
        """
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
        """switch button checked state changed slot"""
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
    """Setting card with spin box"""

    valueChanged = Signal(object)

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase] | None,
        title,
        content=None,
        double: bool = False,
        range: tuple[float, float] | tuple[int, int] | None = None,
        configItem: ConfigItem | None = None,
        is_item: bool = False,
        min_width: int | None = None,
        parent=None,
    ):
        """
        Parameters
        ----------
        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        configItem: ConfigItem
            configuration item operated by the card

        parent: QWidget
            parent widget
        """
        super().__init__(icon, title, is_item, content, parent)
        self.configItem = configItem
        if double:
            from qfluentwidgets import DoubleSpinBox

            self.spinBox = DoubleSpinBox(self)
        else:
            self.spinBox = SpinBox(self)

        if range:
            self.spinBox.setRange(range[0], range[1])  # type: ignore

        if min_width:
            self.spinBox.setMinimumWidth(min_width)

        if configItem:
            self.setValue(qconfig.get(configItem))
            configItem.valueChanged.connect(self.setValue)

        # add switch button to layout
        self.hBoxLayout.addWidget(self.spinBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.spinBox.valueChanged.connect(self.__onValueChanged)

    def __onValueChanged(self, value: int | float):
        """switch spin box value changed slot"""
        self.setValue(value)
        self.valueChanged.emit(value)

    def setValue(self, value: int | float):
        if self.configItem:
            qconfig.set(self.configItem, value)

        self.spinBox.setValue(value)  # type: ignore


class EditSettingCard(BetterSettingCard):
    """Setting card with line edit"""

    valueChanged = Signal(bool)

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase] | None,
        title,
        content=None,
        placeholder_text: str | None = None,
        configItem: ConfigItem | None = None,
        is_item: bool = False,
        parent=None,
    ):
        """
        Parameters
        ----------
        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        configItem: ConfigItem
            configuration item operated by the card

        parent: QWidget
            parent widget
        """
        super().__init__(icon, title, is_item, content, parent)
        self.configItem = configItem
        self.lineEdit = LineEdit(self)
        if placeholder_text:
            self.lineEdit.setPlaceholderText(placeholder_text)

        if configItem:
            self.setText(qconfig.get(configItem))
            configItem.valueChanged.connect(self.setText)

        # add switch button to layout
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.lineEdit.textChanged.connect(self.__onTextChanged)

    def __onTextChanged(self, text: str):
        """switch line edit value changed slot"""
        self.setText(text)
        self.valueChanged.emit(text)

    def setText(self, text: str):
        if self.configItem:
            qconfig.set(self.configItem, text)

        self.lineEdit.setText(text)


class ColorSettingCard(BetterSettingCard):
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
        """
        Parameters
        ----------
        configItem: RangeConfigItem
            configuration item operated by the card

        icon: str | QIcon | FluentIconBase
            the icon to be drawn

        title: str
            the title of card

        content: str
            the content of card

        parent: QWidget
            parent widget

        enableAlpha: bool
            whether to enable the alpha channel
        """
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
