# pyright: reportAttributeAccessIssue=none
from __future__ import annotations

import weakref
from enum import Enum, auto
from typing import Any, assert_never, cast

import qt_pydantic as qtp
from annotated_types import Ge, Gt, Le, Lt
from loguru import logger

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
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

from EasiAuto.common.config import ConfigGroup, ConfigItem
from EasiAuto.view.components.qfw_widgets import SettingIconWidget


class CardType(Enum):
    """设置卡片类型"""

    SWITCH = auto()
    SPIN = auto()
    DOUBLE_SPIN = auto()
    EDIT = auto()
    POSITION = auto()
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
        config_item: ConfigItem | None = None,
        is_item: bool = False,
        item_margin: bool = True,
        parent=None,
        **kwargs,
    ):
        super().__init__(parent=parent)
        self.card_type: CardType = card_type
        self.config_item: ConfigItem | None = config_item
        self.is_item: bool = is_item
        self.item_margin: bool = item_margin
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

        height = 70
        if not content:
            height -= 24
        elif self.is_item:
            height -= 10
        if content and content.count("\n") >= 1:
            height += 15 * content.count("\n") - 10
        self.setFixedHeight(height)

        # 布局
        self.hBoxLayout = QHBoxLayout(self)
        self.vBoxLayout = QVBoxLayout()

        self.hBoxLayout.setSpacing(0)
        self.hBoxLayout.setContentsMargins(48 if self.is_item and self.item_margin else 16, 0, 0, 0)
        self.hBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        if self.has_icon:
            self.hBoxLayout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignLeft)
            self.hBoxLayout.addSpacing(16)

        self.hBoxLayout.addLayout(self.vBoxLayout)
        self.vBoxLayout.addWidget(self.titleLabel, 0, Qt.AlignmentFlag.AlignLeft)
        if content:
            self.vBoxLayout.addWidget(self.contentLabel, 0, Qt.AlignmentFlag.AlignLeft)

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

            case CardType.POSITION:
                # 由两个 SpinBox 组成的复合控件
                self._widget = QWidget(self)
                _layout = QHBoxLayout(self._widget)
                _layout.setContentsMargins(0, 0, 0, 0)
                _layout.setSpacing(6)
                self.xSpinBox = SpinBox(self._widget)
                self.ySpinBox = SpinBox(self._widget)
                self.xSpinBox.setRange(0, 7680)
                self.ySpinBox.setRange(0, 4320)
                self.xSpinBox.setPrefix("X: ")
                self.ySpinBox.setPrefix("Y: ")
                if self.config_item:
                    x, y = self.config_item.value
                    self.xSpinBox.setValue(x)
                    self.ySpinBox.setValue(y)
                self.xSpinBox.valueChanged.connect(lambda v: self._on_value_changed((v, self.ySpinBox.value())))
                self.ySpinBox.valueChanged.connect(lambda v: self._on_value_changed((self.xSpinBox.value(), v)))
                _layout.addWidget(self.xSpinBox)
                _layout.addWidget(self.ySpinBox)

                self.xSpinBox.valueChanged.connect(
                    lambda: self._on_value_changed((self.xSpinBox.value(), self.ySpinBox.value()))
                )
                self.ySpinBox.valueChanged.connect(
                    lambda: self._on_value_changed((self.xSpinBox.value(), self.ySpinBox.value()))
                )

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
        self.hBoxLayout.addWidget(self._widget, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _create_range_widget(self):
        """创建滑条控件（特殊布局）"""
        self._widget = Slider(Qt.Orientation.Horizontal, self)
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
        self.hBoxLayout.addWidget(self.valueLabel, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(6)
        self.hBoxLayout.addWidget(self._widget, 0, Qt.AlignmentFlag.AlignRight)
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
            logger.debug(f"设置修改：({self.config_item.path}) {self.config_item.value} -> {value}")
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
            case CardType.POSITION:
                x, y = value
                self.xSpinBox.setValue(x)
                self.ySpinBox.setValue(y)
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
            case CardType.POSITION:
                return (self.xSpinBox.value(), self.ySpinBox.value())
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
        cls, config_item: ConfigItem | ConfigGroup, is_item=False, item_margin=True, parent: QWidget | None = None
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
            try:
                icon = FluentIcon(icon_name)
            except ValueError:
                logger.warning(f"无法加载图标：{icon_name}")
                icon = None

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
        elif field_type == tuple[int, int]:
            card_type = CardType.POSITION
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
        return cls(
            card_type=card_type,
            icon=icon,
            title=config_item.title,
            content=config_item.description,
            config_item=cast(ConfigItem, config_item),
            is_item=is_item,
            item_margin=item_margin,
            parent=parent,
            **kwargs,
        )

    @classmethod
    def update_all(cls):
        """更新所有配置卡的值"""
        for card in cls.index.values():
            if isinstance(card, ExpandGroupSettingCard):
                continue
            card._initialized = False
            card.updateValue()
            card._initialized = True
