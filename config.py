from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import qt_pydantic as qtp
from loguru import logger
from pydantic import BaseModel, Field, PrivateAttr
from pydantic.fields import FieldInfo
from PySide6.QtGui import QColor

from utils import EA_EXECUTABLE


class LogLevelEnum(Enum):
    TRACE = (5, "追踪")
    DEBUG = (10, "调试")
    INFO = (20, "信息")
    WARNING = (30, "警告")
    ERROR = (40, "错误")
    CRITICAL = (50, "灾难")

    def __init__(self, value, display_name):
        self.display_name = display_name
        self._value_ = value


class LoginMethod(Enum):
    UI_AUTOMATION = (0, "UIA 自动定位")
    OPENCV = (1, "OpenCV 图像识别")
    FIXED_POSITION = (2, "固定位置")

    def __init__(self, value, display_name):
        self.display_name = display_name
        self._value_ = value


class ConfigModel(BaseModel):
    """带自动保存能力的配置模型"""

    _parent: ConfigModel | None = PrivateAttr(default=None)
    _file: Path | None = PrivateAttr(default=None)
    _initialized: bool = PrivateAttr(default=False)

    def model_post_init(self, __context):
        self._initialized = True

    def _root(self) -> ConfigModel:
        root: ConfigModel = self
        while root._parent is not None:
            root = root._parent
        return root

    def save(self):
        root = self._root()
        if root._file is None:
            logger.warning("配置文件路径为空，无法保存")
            return
        data = root.model_dump(mode="json")
        root._file.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")

    def __setattr__(self, name: str, value):
        super().__setattr__(name, value)
        if getattr(self, "_initialized", False) and not name.startswith("_"):
            self.save()

    def _bind_children(self):
        """递归绑定所有子模型的父模型"""
        for value in self.__dict__.values():
            if isinstance(value, ConfigModel):
                value._parent = self
                value._bind_children()

    def attach(self, file: Path):
        self._file = file
        self._parent = None
        self._bind_children()

    def set_by_path(self, parts: tuple[str, ...], value: Any):
        target: Any = self
        for key in parts[:-1]:
            target = getattr(target, key)
        setattr(target, parts[-1], value)

    def iter_items(self) -> Iterable[ConfigItem | ConfigGroup]:
        return iter_config_items(self)


class LoginConfig(ConfigModel):
    Method: LoginMethod = Field(
        default=LoginMethod.UI_AUTOMATION,
        title="登录方式",
        description="选择用于进行自动登录的方式\n可选项：UI Automation - 定位页面元素（推荐，最稳定）、OpenCV - 图像识别、Fixed - 固定位置",
        json_schema_extra={"icon": "Application"},
    )
    SkipOnce: bool = Field(
        default=False,
        title="跳过一次",
        description="下次运行时跳过自动登录，适用于公开课等需临时禁用的场景",
        json_schema_extra={"icon": "Send"},
    )
    KillAgent: bool = Field(
        default=True,
        title="终止 EasiAgent 服务",
        description="可避免某些情况下自动登录被希沃的快捷登录打断",
        json_schema_extra={"icon": "PowerButton"},
    )
    Directly: bool = Field(
        default=False,
        title="跳过点击进入登录界面",
        description="适用于打开希沃时不进入黑板界面（iwb）的情况",
        json_schema_extra={"icon": "People"},
    )
    Is4K: bool = Field(
        default=False,
        title="OpenCV 4K 适配",
        description="在 OpenCV 图像识别 登录方式下，启用对 3840x2160 200% 缩放的支持",
        json_schema_extra={"icon": "FitPage"},
    )

    Timeout: TimeoutConfig = Field(
        default_factory=lambda: TimeoutConfig(),
        title="等待时长",
        description="配置自动登录过程中的等待时长",
        json_schema_extra={"icon": "StopWatch"},
    )
    EasiNote: EasiNoteConfig = Field(
        default_factory=lambda: EasiNoteConfig(),
        title="希沃白板",
        description="配置希沃白板的路径、进程名、窗口标题和启动参数",
        json_schema_extra={"icon": "Application"},
    )


class EasiNoteConfig(ConfigModel):
    AutoPath: bool = Field(default=True, title="自动检测路径", description="启用后，将忽略自定义路径")
    Path: str = Field(
        default=r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe",
        title="自定义路径",
    )
    ProcessName: str = Field(default="EasiNote.exe", title="进程名")
    WindowTitle: str = Field(
        default="希沃白板",
        title="窗口标题",
    )
    Args: str = Field(
        default="",
        title="启动参数",
    )


class TimeoutConfig(ConfigModel):
    # 通用
    Terminate: float = Field(
        default=1,
        ge=0,
        le=5,
        title="终止进程等待时间",
        description="终止希沃白板进程后，重新启动前的等待时间",
    )
    LaunchPollingTimeout: float = Field(
        default=15,
        ge=0,
        le=20,
        title="等待启动超时时间",
        description="希沃白板启动后，等待其启动完成的最大等待时间",
    )
    LaunchPollingInterval: float = Field(
        default=0.5,
        ge=0.5,
        le=2,
        title="等待启动轮询间隔",
        description="轮询检测是否启动完成的时间间隔",
    )
    AfterLaunch: float = Field(
        default=1,
        ge=0,
        le=5,
        title="启动后等待时间",
        description="启动后等待希沃白板界面加载的等待时间",
    )
    # OpenCV 模式独有
    EnterLoginUI: float = Field(
        default=3,
        ge=0,
        le=5,
        title="进入登录界面等待时间",
        description="点击黑板模式下左下角的“登录”按钮后界面出现的等待时间",
    )
    SwitchTab: float = Field(
        default=1,
        ge=0,
        le=5,
        title="切换标签等待时间",
        description="切换到“账号登录”标签页的等待时间",
    )


class WarningConfig(ConfigModel):
    Enabled: bool = Field(
        default=True,
        title="启用警告弹窗",
        description="在运行自动登录前显示警告弹窗，在超时时长内可手动取消登录",
        json_schema_extra={"icon": "Completed"},
    )
    Timeout: int = Field(
        default=60,
        ge=5,
        le=600,
        title="超时时长",
        description="要等待的超时时长（秒）",
        json_schema_extra={"icon": "RemoveFrom"},
    )
    MaxDelays: int = Field(
        default=1,
        ge=0,
        le=3,
        title="最大推迟次数",
        description="最多可以推迟登录的次数",
        json_schema_extra={"icon": "Pause"},
    )
    Delay: int = Field(
        default=150,
        ge=5,
        le=300,
        title="推迟时长",
        description="选择推迟时要等待的时长（秒）",
        json_schema_extra={"icon": "History"},
    )


class BannerConfig(ConfigModel):
    Enabled: bool = Field(
        default=True,
        title="启用警示横幅",
        description="运行自动运行时在屏幕顶部显示一个醒目的警示横幅",
        json_schema_extra={"icon": "Flag"},
    )
    Style: BannerStyleConfig = Field(
        default_factory=lambda: BannerStyleConfig(),
        title="横幅样式",
        description="定制警示横幅的样式与外观",
        json_schema_extra={"icon": "Brush"},
    )


class BannerStyleConfig(ConfigModel):
    Text: str = Field(
        default="  ⚠️WARNING⚠️  正在运行希沃白板自动登录  请勿触摸一体机",
        title="文本",
        description="横幅中滚动的文本内容",
        json_schema_extra={"icon": "Label"},
    )
    TextFont: str = Field(
        default="HarmonyOS Sans SC",
        title="文字字体",
        description="横幅文本使用的字体名称",
        json_schema_extra={"icon": "Font"},
    )
    TextColor: qtp.QColor = Field(
        default=QColor("#FFFFDE59"),
        title="文字颜色",
        description="横幅的文本颜色",
        json_schema_extra={"icon": "Palette", "enable_alpha": True},
    )
    FgColor: qtp.QColor = Field(
        default=QColor("#C8FFDE59"),
        title="前景颜色",
        description="横幅高亮或装饰元素的颜色",
        json_schema_extra={"icon": "Highlight", "enable_alpha": True},
    )
    BgColor: qtp.QColor = Field(
        default=QColor("#B4E4080A"),
        title="背景颜色",
        description="横幅的背景色",
        json_schema_extra={"icon": "BackgroundColor", "enable_alpha": True},
    )
    Fps: int = Field(
        default=60,
        ge=1,
        le=120,
        title="帧率",
        description="横幅的刷新帧率",
        json_schema_extra={"icon": "SpeedHigh", "style": "slider"},
    )
    TextSpeed: int = Field(
        default=3,
        ge=-8,
        le=8,
        title="文字滚动速度",
        description="横幅文本滚动的速度",
        json_schema_extra={"icon": "RightArrow", "style": "slider"},
    )
    YOffset: int = Field(
        default=20, title="垂直偏移", description="横幅距离屏幕顶部的像素偏移量", json_schema_extra={"icon": "Down"}
    )


class AppConfig(ConfigModel):
    MaxRetries: int = Field(
        default=2,
        ge=0,
        le=5,
        title="最大重试次数",
        description="自动登录失败时的最大重试次数",
        json_schema_extra={"icon": "Sync"},
    )
    LogEnabled: bool = Field(
        default=True,
        title="启用日志记录",
        description="在应用 /Logs 目录记录日志文件",
        json_schema_extra={"icon": "Document"},
    )
    EasterEggEnabled: bool = Field(
        default=False,
        title="启用彩蛋",
        description="唔……似乎某些地方有点不对劲的说喵？",
        json_schema_extra={"icon": "Question", "hidden": True},
    )
    DebugMode: bool = Field(
        default=False,
        title="启用开发选项",
        json_schema_extra={"icon": "DeveloperTools", "hidden": True},
    )


class Config(ConfigModel):
    Login: LoginConfig = Field(default_factory=lambda: LoginConfig(), title="登录选项")
    Warning: WarningConfig = Field(default_factory=lambda: WarningConfig(), title="警告弹窗")
    Banner: BannerConfig = Field(default_factory=lambda: BannerConfig(), title="警示横幅")
    App: AppConfig = Field(default_factory=lambda: AppConfig(), title="应用设置")

    @classmethod
    def load(cls, file: str | Path) -> Config:
        path = Path(file)

        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cfg = cls(**data)
            except Exception as e:
                logger.critical(f"配置文件 {file} 解析失败\n错误信息：{e}")
                sys.exit(1)
        else:
            cfg = cls()
            data = cfg.model_dump(mode="json")
            path.write_text(json.dumps(data), encoding="utf-8")
            logger.info(f"配置文件 {file} 不存在，自动生成")

        cfg.attach(path)

        return cfg

    def reset_all(self):
        """重置所有配置为默认值并保存"""
        logger.info("正在重置配置为默认值")
        self._initialized = False

        default_instance = Config()
        for name in Config.model_fields:
            default_value = getattr(default_instance, name)
            setattr(self, name, default_value)
        self._bind_children()

        self._initialized = True
        self.save()
        logger.info("已重置")


@dataclass
class ConfigItem:
    """
    ConfigModel 的单个配置项

    Parameters
    ----------
    path : str
        完整路径，如 "Login.Timeout.Terminate"
    name : str
        字段名，如 "Terminate"
    group : str | None
        字段所属的顶层组路径（如果有），如 "Login.Timeout"
    value : Any
        当前值
    type_ :
        字段类型
    field : FieldInfo
        pydantic 的 FieldInfo，包含 title/description/约束等全部信息
    title : str
        字段标题
    description : str | None
        字段描述
    json_schema_extra : dict[str, Any]
        附加信息
    """

    _root: ConfigModel = field(repr=False)
    _parts: tuple[str, ...] = field(init=False, repr=False)

    path: str
    name: str
    group: str | None
    type_: type[Any]
    field_info: FieldInfo
    title: str
    description: str | None
    json_schema_extra: Any = None
    is_group: bool = False

    def __post_init__(self):
        self._parts = tuple(self.path.split("."))

    @property
    def value(self):
        obj: Any = self._root
        for key in self._parts:
            obj = getattr(obj, key)
        return obj

    @value.setter
    def value(self, new_value: Any):
        self._root.set_by_path(self._parts, new_value)


@dataclass
class ConfigGroup:
    """配置项组"""

    path: str
    name: str
    title: str
    description: str | None
    type_ = ConfigItem
    is_group: bool = True
    json_schema_extra: Any = None
    children: list[ConfigGroup | ConfigItem] = field(default_factory=list)


def iter_config_items(
    obj: ConfigModel, prefix: str = "", group: str | None = None, root: ConfigModel | None = None
) -> list[ConfigItem | ConfigGroup]:
    """
    从任意 ConfigModel 实例递归地枚举出所有字段，并保留层级结构。

    返回一个列表：
    - 根节点的字段直接存在列表中
    - 子模型作为 ConfigGroup，其子字段存在 children 中
    """
    cls = type(obj)
    result: list[ConfigItem | ConfigGroup] = []
    if root is None:
        root = obj

    for name, field_info in cls.model_fields.items():
        value = getattr(obj, name)
        path = f"{prefix}.{name}" if prefix else name

        if isinstance(value, ConfigModel):
            # 递归获取子节点
            children = iter_config_items(value, prefix=path, group=group, root=root)

            group_node = ConfigGroup(
                path=path,
                name=name,
                title=field_info.title or name,
                description=field_info.description,
                json_schema_extra=field_info.json_schema_extra,
                children=children,
            )
            result.append(group_node)
        else:
            item_node = ConfigItem(
                path=path,
                name=name,
                group=group,
                type_=field_info.annotation or type(value),
                field_info=field_info,
                title=field_info.title or name,
                description=field_info.description,
                json_schema_extra=field_info.json_schema_extra,
                _root=root,
            )
            result.append(item_node)

    return result


config = Config.load(EA_EXECUTABLE.parent / "config.json")
