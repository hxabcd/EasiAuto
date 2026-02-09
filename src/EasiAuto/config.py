from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import qt_pydantic as qtp
from loguru import logger
from pydantic import BaseModel, Field, PrivateAttr
from pydantic.fields import FieldInfo

from PySide6.QtGui import QColor

from EasiAuto.consts import EA_BASEDIR


class InformativeEnum(Enum):
    """带显示名称的枚举类"""

    def __init__(self, value, display_name):
        self.display_name = display_name
        self._value_ = value


class LogLevelEnum(InformativeEnum):
    TRACE = (5, "追踪")
    DEBUG = (10, "调试")
    INFO = (20, "信息")
    WARNING = (30, "警告")
    ERROR = (40, "错误")
    CRITICAL = (50, "灾难")


class LoginMethod(InformativeEnum):
    UI_AUTOMATION = (0, "UIA 自动定位")
    OPENCV = (1, "OpenCV 图像识别")
    FIXED_POSITION = (2, "固定位置")


class ThemeOptions(InformativeEnum):
    AUTO = ("Auto", "跟随系统")
    LIGHT = ("Light", "浅色")
    DARK = ("Dark", "深色")


class UpdateMode(InformativeEnum):
    NEVER = (0, "从不自动更新")
    CHECK_AND_NOTIFY = (1, "自动检查更新并通知")
    CHECK_AND_DOWNLOAD = (2, "自动检查更新并下载")
    CHECK_AND_INSTALL = (3, "自动检查更新并安装")


class UpdateChannal(InformativeEnum):
    RELEASE = ("release", "稳定通道")
    DEV = ("dev", "测试通道")


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
        try:
            data = root.model_dump(mode="json")
            root._file.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        except Exception as e:
            logger.error(f"保存配置文件库失败: {e}")

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

    def iter_items(
        self,
        only: list[str] = [],
        exclude: list[str] = [],
    ) -> list[ConfigItem | ConfigGroup]:
        return iter_config_items(self, only=only, exclude=exclude)


class LoginConfig(ConfigModel):
    Method: LoginMethod = Field(
        default=LoginMethod.UI_AUTOMATION,
        title="登录方式",
        description="选择用于进行自动登录的方式（OpenCV仅支持常规分辨率与缩放）\nUIA 最稳定 / OpenCV 较快 / 固定位置暂不可用",
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
        description="配置自动登录过程中的等待时长（秒）",
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
    DelayTime: int = Field(
        default=150,
        ge=5,
        le=300,
        title="推迟时长",
        description="选择推迟时要等待的时长（秒）",
        json_schema_extra={"icon": "History"},
        alias="Delay",
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
    Theme: ThemeOptions = Field(
        default=ThemeOptions.AUTO,
        title="应用主题",
        description="控制应用的明暗主题",
        json_schema_extra={"icon": "Constract"},
    )
    LogEnabled: bool = Field(
        default=True,
        title="启用日志记录",
        description="在应用 /logs 目录记录日志文件，以便于进行调试和问题排查",
        json_schema_extra={"icon": "Document"},
    )
    TelemetryEnabled: bool = Field(
        default=True,
        title="启用遥测",
        description="通过 Sentry SDK 收集此应用的错误信息以帮助我们改进此应用\n你的信息会匿名上传，且不会包含任何你的个人信息。你随时可以手动关闭该选项",
        json_schema_extra={"icon": "Feedback"},
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


class ClassIslandConfig(ConfigModel):
    AutoPath: bool = Field(
        default=False,
        title="自动获取路径",
        description="自动获取 ClassIsland 的路径",
    )
    Path: str = Field(
        default="",
        title="自定义路径",
        description="自定义 ClassIsland 的路径",
    )
    DefaultDisplayName: str = Field(
        default="自动登录希沃白板",
        title="默认显示名称",
        description="（重启生效）",
    )
    DefaultPreTime: int = Field(
        default=300,
        ge=0,
        le=1800,
        title="默认提前时长",
        description="（重启生效）",
    )


class UpdateConfig(ConfigModel):
    Mode: UpdateMode = Field(
        default=UpdateMode.CHECK_AND_INSTALL,
        title="更新模式",
        description="设置应用的更新模式",
        json_schema_extra={"icon": "Application"},
    )
    Channal: UpdateChannal = Field(
        default=UpdateChannal.RELEASE,
        title="更新通道",
        description="控制应用的更新目标版本（测试通道可能含有不稳定的功能，谨慎使用）",
        json_schema_extra={"icon": "Tag"},
    )
    CheckAfterLogin: bool = Field(
        default=True,
        title="登录后更新",
        description="登录完成后，尝试按照设置的更新模式检查更新（安装时将会静默）",
        json_schema_extra={"icon": "Megaphone"},
    )
    UseMirror: bool = Field(
        default=False,
        title="使用镜像",
        description="下载较慢时，可尝试启用镜像源下载 (ghproxy)",
        json_schema_extra={"icon": "Download"},
    )

    LastVersion: str = Field(
        default="Unknown",
        title="上个版本",
        description="用于在更新完成后下一次启动应用显示更新成功提示",
        json_schema_extra={"hidden": True},
    )


class Config(ConfigModel):
    Login: LoginConfig = Field(default_factory=lambda: LoginConfig(), title="登录选项")
    Warning: WarningConfig = Field(default_factory=lambda: WarningConfig(), title="警告弹窗")
    Banner: BannerConfig = Field(default_factory=lambda: BannerConfig(), title="警示横幅")
    App: AppConfig = Field(default_factory=lambda: AppConfig(), title="应用设置")

    Update: UpdateConfig = Field(default_factory=lambda: UpdateConfig(), title="更新设置")
    ClassIsland: ClassIslandConfig = Field(default_factory=lambda: ClassIslandConfig(), title="ClassIsland 设置")

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
            path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
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
    obj: ConfigModel,
    prefix: str = "",
    group: str | None = None,
    root: ConfigModel | None = None,
    only: list[str] = [],
    exclude: list[str] = [],
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

        if (only and not any(o in path for o in only)) or (exclude and any(e in path for e in exclude)):
            continue

        if extra := field_info.json_schema_extra:
            if extra.get("hidden", False):  # type: ignore
                continue

        if isinstance(value, ConfigModel):
            # 递归获取子节点
            children = iter_config_items(value, prefix=path, group=group, root=root, only=only, exclude=exclude)

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


config = Config.load(EA_BASEDIR / "config.json")
