from typing import Literal

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QMessageBox,
    QWidget,
)
from qfluentwidgets import (
    isDarkTheme,
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


class Separator(QWidget):
    """通用分隔符"""

    def __init__(self, direction: Literal["vertical", "horizontal"] = "horizontal", parent=None):
        super().__init__(parent=parent)
        self.direction = direction
        if direction == "vertical":
            self.setFixedWidth(3)
        else:
            self.setFixedHeight(3)

    def paintEvent(self, e):
        painter = QPainter(self)
        c = 255 if isDarkTheme() else 0
        pen = QPen(QColor(c, c, c, 15))
        pen.setCosmetic(True)
        painter.setPen(pen)
        if self.direction == "vertical":
            painter.drawLine(1, 0, 1, self.height())
        else:
            painter.drawLine(0, 1, self.width(), 1)


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

        font_families = ["Microsoft YaHei UI", "sans-serif"]
        if self.config.TextFont != "":
            font_families.insert(0, self.config.TextFont)
        font = QFont(font_families, pointSize=36, weight=QFont.Bold)
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
