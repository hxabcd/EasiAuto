from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from qfluentwidgets import (
    BoolValidator,
    ColorConfigItem,
    ConfigItem,
    OptionsConfigItem,
    OptionsValidator,
    QConfig,
    RangeConfigItem,
    RangeValidator,
)

get_log_level = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


class WarningConfig(BaseModel):
    Enabled: bool = True
    Timeout: int = Field(60, ge=5, le=300)


class BannerConfig(BaseModel):
    Enabled: bool = True
    Text: str = "  ⚠️WARNING⚠️  正在运行希沃白板自动登录  请勿触摸一体机"
    YOffset: int = 20
    Fps: int = Field(30, ge=1, le=120)
    BgColor: str = "#B4E4080A"
    FgColor: str = "#C8FFDE59"
    TextColor: str = "#FFFFDE59"
    TextFont: str = ""
    TextSpeed: int = 3


class EasiNoteConfig(BaseModel):
    AutoPath: bool = True
    Path: str = r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe"
    ProcessName: str = "EasiNote.exe"
    WindowTitle: str = "希沃白板"
    Args: str = ""


class TimeoutConfig(BaseModel):
    Terminate: int = Field(1, ge=0, le=5)
    LaunchPollingTimeout: int = Field(15, ge=0, le=20)
    LaunchPollingInterval: float = Field(0.5, ge=0.5, le=2)
    AfterLaunch: int = Field(1, ge=0, le=5)
    EnterLoginUI: int = Field(3, ge=0, le=5)
    SwitchTab: int = Field(1, ge=0, le=5)


class LoginConfig(BaseModel):
    Method: Literal["UIAutomation", "OpenCV", "FixedPosition"] = "UIAutomation"
    SkipOnce: bool = False
    KillAgent: bool = True
    Is4K: bool = False
    Directly: bool = False


class AppConfig(BaseModel):
    MaxRetries: int = Field(2, ge=0, le=5)
    LogLevel: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "WARNING"


class Config(BaseModel):
    Warning: WarningConfig = Field(default_factory=WarningConfig)  # type: ignore
    Banner: BannerConfig = Field(default_factory=BannerConfig)  # type: ignore
    EasiNote: EasiNoteConfig = Field(default_factory=EasiNoteConfig)
    Timeout: TimeoutConfig = Field(default_factory=TimeoutConfig)  # type: ignore
    Login: LoginConfig = Field(default_factory=LoginConfig)
    App: AppConfig = Field(default_factory=AppConfig)  # type: ignore

    @classmethod
    def load(cls, file: str = "config.json") -> Config:
        path = Path(file)
        if path.exists() and path.stat().st_size > 0:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cfg = cls(**data)
            except Exception as e:
                logging.error(f"配置文件解析失败，请检查 {file} 内容是否正确！\n错误信息：{e}")
                sys.exit(1)
        else:
            cfg = cls()

        return cfg


class QfwEasiautoConfig(QConfig):
    """Easiauto UI 应用配置"""

    # 主题色配置
    themeColor = ColorConfigItem("QFluentWidgets", "ThemeColor", "#00C884")

    # 警告弹窗配置
    warningEnabled = ConfigItem("Warning", "Enabled", True, BoolValidator())
    warningTimeout = RangeConfigItem("Warning", "Timeout", 60, RangeValidator(5, 300))

    # 警示横幅配置
    bannerEnabled = ConfigItem("Banner", "Enabled", True, BoolValidator())
    bannerText = ConfigItem("Banner", "Text", "  ⚠️WARNING⚠️  正在运行希沃白板自动登录  请勿触摸一体机")
    bannerYOffset = RangeConfigItem("Banner", "YOffset", 20)
    bannerFps = RangeConfigItem("Banner", "Fps", 30, RangeValidator(1, 120))
    bannerBgColor = ColorConfigItem("Banner", "BgColor", "#B4E4080A")
    bannerFgColor = ColorConfigItem("Banner", "FgColor", "#C8FFDE59")
    bannerTextColor = ColorConfigItem("Banner", "TextColor", "#FFFFDE59")
    bannerTextFont = ConfigItem("Banner", "TextFont", "")
    bannerTextSpeed = RangeConfigItem("Banner", "TextSpeed", 3, RangeValidator(1, 12))

    # 希沃白板配置
    easinoteAutoPath = ConfigItem("EasiNote", "AutoPath", True, BoolValidator())
    easinotePath = ConfigItem(
        "EasiNote", "Path", r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe"
    )
    easinoteProcessName = ConfigItem("EasiNote", "ProcessName", "EasiNote.exe")
    easinoteWindowTitle = ConfigItem("EasiNote", "WindowTitle", "希沃白板")
    easinoteArgs = ConfigItem("EasiNote", "Args", "")

    # 超时配置
    timeoutTerminate = RangeConfigItem("Timeout", "Terminate", 1, RangeValidator(0, 5))
    timeoutLaunchPollingTimeout = RangeConfigItem("Timeout", "LaunchPollingTimeout", 15, RangeValidator(0, 20))
    timeoutLaunchPollingInterval = RangeConfigItem("Timeout", "LaunchPollingInterval", 0.5, RangeValidator(0.5, 2))
    timeoutAfterLaunch = RangeConfigItem("Timeout", "AfterLaunch", 1, RangeValidator(0, 5))
    timeoutEnterLoginUI = RangeConfigItem("Timeout", "EnterLoginUI", 3, RangeValidator(0, 5))
    timeoutSwitchTab = RangeConfigItem("Timeout", "SwitchTab", 1, RangeValidator(0, 5))

    # 登录配置
    loginMethod = OptionsConfigItem(
        "Login", "Method", "UIAutomation", OptionsValidator(["UIAutomation", "OpenCV", "FixedPosition"])
    )
    loginSkipOnce = ConfigItem("Login", "SkipOnce", False, BoolValidator())
    loginKillAgent = ConfigItem("Login", "KillAgent", True, BoolValidator())
    loginIs4K = ConfigItem("Login", "Is4K", False, BoolValidator())
    loginDirectly = ConfigItem("Login", "Directly", False, BoolValidator())

    # 应用配置
    appMaxRetries = RangeConfigItem("App", "MaxRetries", 2, RangeValidator(0, 5))
    appLogLevel = OptionsConfigItem(
        "App", "LogLevel", "WARNING", OptionsValidator(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    )
