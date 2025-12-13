from __future__ import annotations

import logging
import weakref
from enum import Enum, auto
from typing import Any, Literal, assert_never

import qt_pydantic as qtp
from annotated_types import Ge, Gt, Le, Lt
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
    ComboBox,
    DoubleSpinBox,
    ExpandGroupSettingCard,
    FluentIcon,
    FluentStyleSheet,
    LineEdit,
    Slider,
    SpinBox,
    SwitchButton,
    isDarkTheme,
)

from config import BannerConfig, ConfigGroup, ConfigItem
from qfw_widgets import SettingIconWidget
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


class CardType(Enum):
    """设置卡片类型"""

    SWITCH = auto()
    SPIN = auto()
    DOUBLE_SPIN = auto()
    EDIT = auto()
    COLOR = auto()
    RANGE = auto()
    ENUM = auto()


class SettingCard(QFrame):
    """
    统一设置卡片

    整合了所有类型的设置卡片：开关、数字输入、文本输入、颜色选择、滑条

    Parameters
    ----------
    card_type: CardType
        卡片类型
    icon: str | QIcon | FluentIcon | None
        图标，可为空
    title: str
        标题
    content: str | None
        描述内容
    configItem: ConfigItem | None
        配置项
    is_item: bool
        是否为列表项（去除边框）
    parent: QWidget | None
        父组件
    **kwargs:
        各类型特有参数：
        - 通用: min_width(int)
        - EDIT: placeholder_text(str)
        - COLOR: enable_alpha(bool)
    """

    valueChanged = Signal(object)
    index: weakref.WeakValueDictionary[str, SettingCard | ExpandGroupSettingCard] = weakref.WeakValueDictionary()

    def __init__(
        self,
        card_type: CardType,
        icon: str | QIcon | FluentIcon | None,
        title: str,
        content: str | None = None,
        config_item: ConfigItem | ConfigGroup | None = None,
        is_item: bool = False,
        parent=None,
        **kwargs,
    ):
        super().__init__(parent=parent)
        self.card_type: CardType = card_type
        self.config_item: ConfigItem | ConfigGroup | None = config_item
        self.is_item: bool = is_item
        self._widget: QWidget  # 主控件
        self._initialized = False

        if self.config_item:
            self.setObjectName(self.config_item.path)

        # 初始化基础布局
        self._init_base_layout(icon, title, content)

        # 根据类型创建控件
        self._create_widget(card_type, title, **kwargs)
        if self.config_item:
            self.setValue(self.config_item.value)

        self._initialized = True

        FluentStyleSheet.SETTING_CARD.apply(self)

    def _init_base_layout(self, icon, title: str, content: str | None):
        """初始化基础布局"""
        self.has_icon = icon is not None

        if self.has_icon:
            self.iconLabel = SettingIconWidget(icon, self)
            self.iconLabel.setFixedSize(16, 16)
        self.titleLabel = QLabel(title, self)
        self.contentLabel = QLabel(content or "", self)
        self.contentLabel.setObjectName("contentLabel")

        if not content:
            self.contentLabel.hide()

        self.setFixedHeight(70 if content else 50)
        # 布局
        self.hBoxLayout = QHBoxLayout(self)
        self.vBoxLayout = QVBoxLayout()

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

    def _parse_range(self):
        if self.config_item:
            # 设置数值范围
            metadata = self.config_item.field_info.metadata

            min_val = None
            max_val = None

            for constraint in metadata:
                match constraint:
                    case Ge(ge=val):
                        min_val = val
                    case Gt(gt=val):
                        min_val = val
                    case Le(le=val):
                        max_val = val
                    case Lt(lt=val):
                        max_val = val

            if min_val is None or max_val is None:
                return None

            return min_val, max_val
        return None

    def parse_range_float(self):
        if range := self._parse_range():
            a, b = range
            return float(a), float(b)  # type: ignore
        return None

    def parse_range_int(self):
        if range := self._parse_range():
            a, b = range
            return int(a), int(b)  # type: ignore
        return None

    def _create_widget(self, card_type: CardType, title: str, **kwargs):
        """根据类型创建控件"""
        match card_type:
            case CardType.SWITCH:
                self._widget = self.switchButton = SwitchButton(self)
                if self.config_item:
                    self._widget.setChecked(self.config_item.value)
                self._widget.checkedChanged.connect(self._on_value_changed)

            case CardType.SPIN:
                self._widget = SpinBox(self)
                if range := self.parse_range_int():
                    self._widget.setRange(*range)
                self._widget.valueChanged.connect(self._on_value_changed)

            case CardType.DOUBLE_SPIN:
                self._widget = DoubleSpinBox(self)
                if range := self.parse_range_float():
                    self._widget.setRange(*range)
                self._widget.valueChanged.connect(self._on_value_changed)

            case CardType.EDIT:
                self._widget = LineEdit(self)
                if self.config_item:
                    extra = self.config_item.json_schema_extra or {}
                    if text := extra.get("placeholder_text"):
                        self._widget.setPlaceholderText(text)
                    else:
                        self._widget.setPlaceholderText(self.config_item.field_info.default)
                self._widget.textChanged.connect(self._on_value_changed)

            case CardType.COLOR:
                enable_alpha = False
                if self.config_item:
                    extra = self.config_item.json_schema_extra or {}
                    if value := extra.get("enable_alpha"):
                        enable_alpha = value
                initial_color = self.config_item.field_info.default if self.config_item else QColor()
                self._widget = ColorPickerButton(initial_color, title, self, enable_alpha)
                self._widget.colorChanged.connect(self._on_value_changed)

            case CardType.RANGE:
                self._create_range_widget()
                return  # Range 有特殊布局，提前返回

            case CardType.ENUM:
                self._create_combo_box()

            case unreachable:
                assert_never(unreachable)

        # 添加控件到布局
        self.hBoxLayout.addWidget(self._widget, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _create_range_widget(self):
        """创建滑条控件（特殊布局）"""
        self._widget = Slider(Qt.Horizontal, self)
        self.valueLabel = QLabel(self)
        self.valueLabel.setObjectName("valueLabel")

        self._widget.setMinimumWidth(268)
        self._widget.setSingleStep(1)

        if self.config_item:
            if range := self.parse_range_int():
                self._widget.setRange(*range)
            self._widget.setValue(self.config_item.value)
            self.valueLabel.setNum(self.config_item.value)

        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.valueLabel, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(6)
        self.hBoxLayout.addWidget(self._widget, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self._widget.valueChanged.connect(self._on_value_changed)

    def _create_combo_box(self):
        """创建下拉框控件"""
        self._widget = ComboBox(self)

        if self.config_item and issubclass(self.config_item.type_, Enum):
            # 加载枚举项
            options = list(self.config_item.type_)
            self.options_index = []
            for option in options:
                name = getattr(option, "display_name", option.name)
                self.options_index.append(option)
                self._widget.addItem(name, userData=option)

            # 设置当前值
            current_value: Enum = self.config_item.value
            current_index = -1
            for i, opt in enumerate(options):
                if opt == current_value:
                    current_index = i
                    break
            if current_index >= 0:
                self._widget.setCurrentIndex(current_index)

        self._widget.currentIndexChanged.connect(lambda i: self._on_value_changed(self.options_index[i]))

    def _on_value_changed(self, value: Any):
        """值变化处理"""
        if self.config_item and self._initialized:
            logging.debug(f"设置修改：({self.config_item.path}) {self.config_item.value} -> {value}")
            self.config_item.value = value
        if self.card_type == CardType.RANGE:  # 同步数值标签
            self.valueLabel.setNum(value)
            self.valueLabel.adjustSize()
        self.valueChanged.emit(value)

    def updateValue(self):
        if not self.config_item:
            return

        value = self.config_item.value
        self.setValue(value)

    def setValue(self, value: Any):
        match self.card_type:
            case CardType.SWITCH:
                self._widget.setChecked(value)
            case CardType.SPIN | CardType.DOUBLE_SPIN:
                self._widget.setValue(value)
            case CardType.EDIT:
                self._widget.setText(value)
            case CardType.COLOR:
                self._widget.setColor(value)
            case CardType.RANGE:
                self._widget.setValue(value)
                self.valueLabel.setNum(value)
                self.valueLabel.adjustSize()
            case CardType.ENUM:
                name = getattr(value, "display_name", value.name)
                self._widget.setCurrentText(name)
            case unreachable:
                assert_never(unreachable)

    def getValue(self) -> Any:
        match self.card_type:
            case CardType.SWITCH:
                return self._widget.isChecked()
            case CardType.SPIN | CardType.DOUBLE_SPIN | CardType.RANGE:
                return self._widget.value()
            case CardType.EDIT:
                return self._widget.text()
            case CardType.COLOR:
                return self._widget.color
            case CardType.ENUM:
                return self._widget.currentData()
            case unreachable:
                assert_never(unreachable)
        return None

    def setObjectName(self, name: str):
        super().setObjectName(name)
        if name:
            type(self).index[name] = self  # 绑定至索引

    # ============ 便捷属性/方法 ============

    def isChecked(self) -> bool:
        """获取开关状态（仅 SWITCH 类型）"""
        if self.card_type == CardType.SWITCH:
            return self._widget.isChecked()
        raise TypeError("isChecked() only available for SWITCH type")

    def setChecked(self, checked: bool):
        """设置开关状态（仅 SWITCH 类型）"""
        if self.card_type == CardType.SWITCH:
            self.setValue(checked)
        else:
            raise TypeError("setChecked() only available for SWITCH type")

    def setText(self, text: str):
        """设置文本（仅 EDIT 类型）"""
        if self.card_type == CardType.EDIT:
            self.setValue(text)
        else:
            raise TypeError("setText() only available for EDIT type")

    def setTitle(self, title: str):
        """设置标题"""
        self.titleLabel.setText(title)

    def setContent(self, content: str):
        """设置描述内容"""
        self.contentLabel.setText(content)
        self.contentLabel.setVisible(bool(content))

    def setIconSize(self, width: int, height: int):
        """设置图标大小"""
        if self.has_icon:
            self.iconLabel.setFixedSize(width, height)

    @property
    def widget(self):
        """获取主控件，用于自定义操作"""
        return self._widget

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

    @classmethod
    def from_config(
        cls, config_item: ConfigItem | ConfigGroup, is_item=False, parent: QWidget | None = None
    ) -> SettingCard | ExpandGroupSettingCard:
        """
        根据 ConfigItem 或 ConfigGroup 的类型和元数据创建对应的 SettingCard

        Parameters
        ----------
        config_item: ConfigItem | ConfigGroup
            配置项
        parent: QWidget
            父组件

        Return
        ----------
        创建的设置卡片
        """

        # 获取附加信息
        extra = config_item.json_schema_extra or {}

        icon: FluentIcon | QIcon | None = None
        if icon_name := extra.get("icon"):
            icon = FluentIcon(icon_name)

        kwargs: dict[str, Any] = {}
        supported_args = []  # 暂时弃用，已被动态注入（应该算吧？）取代
        for arg in supported_args:
            if arg in extra:
                kwargs[arg] = extra[arg]

        # 判断卡片类型
        card_type: CardType | None = None
        field_type = config_item.type_
        style = extra.get("style")

        if field_type is bool:
            card_type = CardType.SWITCH
        elif field_type in (int, float):
            if style == "slider":
                card_type = CardType.RANGE
            elif field_type is float:
                card_type = CardType.DOUBLE_SPIN
            else:
                card_type = CardType.SPIN
        elif field_type is str:
            card_type = CardType.EDIT
        elif field_type in (QColor, qtp.QColor):
            card_type = CardType.COLOR
        elif issubclass(field_type, Enum):
            card_type = CardType.ENUM
        elif field_type is ConfigItem:
            group_container = ExpandGroupSettingCard(
                icon=icon or QIcon(),
                title=config_item.title,
                content=config_item.description,  # type: ignore
            )

            group_container.setObjectName(config_item.path)
            cls.index[config_item.path] = group_container

            for item in config_item.children:
                group_container.addGroupWidget(cls.from_config(item, is_item=True))

            return group_container
        else:
            raise TypeError(f"无法推断 {config_item.path} 的数据类型")

        # 创建卡片
        card = cls(
            card_type=card_type,
            icon=icon,
            title=config_item.title,
            content=config_item.description,
            config_item=config_item,
            is_item=is_item,
            parent=parent,
            **kwargs,
        )

        return card

    @classmethod
    def update_all(cls):
        """更新所有配置卡的值"""
        for card in cls.index.values():
            if isinstance(card, ExpandGroupSettingCard):
                continue
            card._initialized = False
            card.updateValue()
            card._initialized = True
