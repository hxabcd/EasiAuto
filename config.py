from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, Field, PrivateAttr

get_log_level = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


T = TypeVar("T", bound=BaseModel)


class AutoSaveModel(BaseModel):
    """带自动保存能力的基类"""

    # 私有属性：父级引用、文件路径
    _parent: AutoSaveModel | None = PrivateAttr(default=None)
    _file: Path | None = PrivateAttr(default=None)

    def save(self) -> None:
        """触发根配置的保存"""
        root = self
        while root._parent is not None:
            root = root._parent
        if root._file is not None:
            data = root.model_dump(exclude_none=True)
            root._file.write_text(json.dumps(data), encoding="utf-8")

    def __setattr__(self, name: str, value) -> None:
        super().__setattr__(name, value)
        if not name.startswith("_"):  # 修改字段时触发保存
            self.save()

    def _bind_children(self) -> None:
        """递归绑定所有子模型的 _parent 和 _file"""
        for name, value in self.__dict__.items():
            if isinstance(value, AutoSaveModel):
                value._parent = self
                value._file = self._file
                value._bind_children()  # 递归绑定


class WarningConfig(AutoSaveModel):
    enabled: bool = False
    timeout: int = Field(15, ge=5, le=300)


class BannerConfig(AutoSaveModel):
    enabled: bool = True
    text: str = "  ⚠️WARNING⚠️  正在运行希沃白板自动登录  请勿触摸一体机"
    y_offset: int = 20


class EasiNoteConfig(AutoSaveModel):
    path: str = "auto"
    process_name: str = "EasiNote.exe"
    window_title: str = "希沃白板"
    args: str = ""


class TimeoutConfig(AutoSaveModel):
    terminate: int = Field(1, gt=0, le=30)
    launch_polling_timeout: int = Field(15, gt=0, le=30)
    launch_polling_interval: float = Field(0.5, gt=0, le=5)
    after_launch: int = Field(1, ge=0, le=5)
    enter_login_ui: int = Field(3, ge=0, le=30)
    switch_tab: int = Field(1, ge=0, le=30)


class LoginConfig(AutoSaveModel):
    skip_once: bool = False
    kill_agent: bool = True
    is_4k: bool = False
    directly: bool = False
    easinote: EasiNoteConfig = Field(default_factory=EasiNoteConfig)
    timeout: TimeoutConfig = Field(default_factory=TimeoutConfig)  # type: ignore


class AppConfig(AutoSaveModel):
    max_retries: int = Field(2, ge=0, le=10)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "WARNING"


class Config(AutoSaveModel):
    warning: WarningConfig = Field(default_factory=WarningConfig)  # type: ignore
    banner: BannerConfig = Field(default_factory=BannerConfig)
    login: LoginConfig = Field(default_factory=LoginConfig)
    app: AppConfig = Field(default_factory=AppConfig)  # type: ignore

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

        cfg._file = path
        cfg._bind_children()
        return cfg
