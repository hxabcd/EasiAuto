from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from EasiAuto.common.config import BannerStyleConfig


class WarningBanner(QWidget):
    """顶部警示横幅"""

    def __init__(self, config: BannerStyleConfig):
        super().__init__()
        self.config = config

        self.setFixedHeight(140)  # 横幅高度
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 置顶、无边框、点击穿透
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )

        self.text_x = 0

        font_families = ["Microsoft YaHei UI", "sans-serif"]
        if self.config.TextFont != "":
            font_families.insert(0, self.config.TextFont)
        font = QFont(font_families, pointSize=36, weight=QFont.Weight.Bold)
        self.text_font = font

        # 生成斜纹
        self.stripe = QPixmap(40, 32)
        self.stripe.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self.stripe)
        painter.setBrush(QColor(self.config.FgColor))
        painter.setPen(Qt.PenStyle.NoPen)
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
        self.text_x -= self.config.TextSpeed
        # 文字总长度
        total_text_width = QFontMetrics(self.text_font).horizontalAdvance(self.config.Text)
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
        text_width = painter.fontMetrics().horizontalAdvance(self.config.Text)
        x = self.text_x
        while x < self.width():
            painter.drawText(x, int(self.height() / 2 + self.config.YOffset), self.config.Text)
            x += text_width
