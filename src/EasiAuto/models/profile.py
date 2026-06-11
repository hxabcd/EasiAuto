from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from cryptography.fernet import InvalidToken
from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializationInfo,
    field_serializer,
    field_validator,
    model_serializer,
)

from PySide6.QtCore import QObject, Signal

from EasiAuto.consts import EA_PREFIX, PROFILE_PATH
from EasiAuto.core.security import get_profile_cipher
from EasiAuto.models.config import config

_PROFILE_SCHEMA_VERSION = 2
_SECRET_TOKEN_PREFIX = f"ea{_PROFILE_SCHEMA_VERSION}$"

ProfileChangeReason = Literal[
    "profile_changed",
    "automation_saved",
    "automation_deleted",
    "encryption_changed",
]


class ProfileNotifier(QObject):
    changed = Signal(str)


def encrypt_secret(plaintext: str) -> str:
    if plaintext == "":
        return plaintext
    cipher = get_profile_cipher()
    token = cipher.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_SECRET_TOKEN_PREFIX}{token}"


def decrypt_secret(token: str) -> str:
    if token == "" or not token.startswith(_SECRET_TOKEN_PREFIX):
        return token
    cipher = get_profile_cipher()
    raw = token.removeprefix(_SECRET_TOKEN_PREFIX)
    try:
        return cipher.decrypt(raw.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("密文校验失败或密钥不可用") from e


class BaseAutomation(BaseModel, ABC):
    """自动登录档案基类"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str | None = Field(default=None, description="档案名称")
    enabled: bool = Field(default=True, description="是否启用")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    type: str

    @property
    @abstractmethod
    def display_name(self) -> str | None: ...

    @property
    @abstractmethod
    def detail_name(self) -> str | None: ...

    @property
    @abstractmethod
    def export_name(self) -> str: ...

    def get_automation_name(self, subject_name: str | None) -> str:
        text = f"{EA_PREFIX} {config.ClassIsland.DefaultDisplayName}"
        if subject_name and self.name:
            text += f" - {subject_name} ({self.name})"
        elif t := (subject_name or self.display_name):
            text += f" - {t}"
        return text


class EasiAutomation(BaseAutomation):
    """账密登录档案"""

    type: Literal["password"] = Field(default="password")

    account: str = Field(default="", description="账号")
    password: str = Field(default="", description="密码")
    account_name: str | None = Field(default=None, description="希沃白板用户名")
    avatar: Any | None = Field(default=None, description="希沃白板头像")

    @model_serializer(mode="wrap")
    def check_on_dump(self, serializer):
        if not self.account.strip():
            raise ValueError("账号不能为空")
        if not self.password.strip():
            raise ValueError("密码不能为空")
        return serializer(self)

    @property
    def display_name(self) -> str | None:
        return self.name or self.account_name

    @property
    def detail_name(self) -> str | None:
        return self.account or None

    @property
    def automation_name(self) -> str:
        return f"{EA_PREFIX} {config.ClassIsland.DefaultDisplayName}" + (f" - {self.name}" if self.name else "")

    @property
    def export_name(self) -> str:
        label = self.name or self.account
        return f"希沃自动登录（{label}）"

    @field_serializer("password", mode="plain")
    def _ser_password(self, value: str, _info: SerializationInfo) -> str:
        if _info.context and _info.context.get("encryption_enabled"):
            return encrypt_secret(value)
        return value

    @field_validator("password", mode="after")
    @classmethod
    def _deser_password(cls, value: str) -> str:
        try:
            return decrypt_secret(value)
        except Exception as e:
            logger.error(f"解密密码失败: {e}")
            return ""


class QrcodeAutomation(BaseAutomation):
    """二维码登录档案"""

    type: Literal["qrcode"] = Field(default="qrcode")

    token: str = Field(default="", description="二维码登录令牌")
    user_id: str | None = Field(default=None, description="希沃用户 ID")
    nick_name: str | None = Field(default=None, description="希沃用户昵称")
    phone: str | None = Field(default=None, description="希沃用户手机号")
    avatar: Any | None = Field(default=None, description="希沃用户头像")

    @model_serializer(mode="wrap")
    def check_on_dump(self, serializer):
        if not self.token.strip():
            raise ValueError("令牌不能为空")
        return serializer(self)

    @property
    def display_name(self) -> str | None:
        return self.name or self.nick_name

    @property
    def detail_name(self) -> str | None:
        return "二维码档案"

    @property
    def export_name(self) -> str:
        label = self.name or self.nick_name or self.user_id or "未命名"
        return f"希沃自动登录（{label}）"

    @field_serializer("token")
    def _ser_token(self, value: str, _info: SerializationInfo) -> str:
        if _info.context and _info.context.get("encryption_enabled"):
            return encrypt_secret(value)
        return value

    @field_validator("token", mode="after")
    @classmethod
    def _deser_token(cls, value: str) -> str:
        try:
            return decrypt_secret(value)
        except Exception as e:
            logger.error(f"解密令牌失败: {e}")
            return ""


Automation = Annotated[
    EasiAutomation | QrcodeAutomation,
    Field(discriminator="type"),
]


class Profile(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_version: int = Field(default=_PROFILE_SCHEMA_VERSION)
    encryption_enabled: bool = Field(default=True, description="是否启用档案密码加密")

    automations: list[Automation] = Field(default_factory=list)
    notifier: ProfileNotifier = Field(default_factory=ProfileNotifier, exclude=True)

    @classmethod
    def _load_raw_payload(cls, path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def save(self, reason: ProfileChangeReason = "profile_changed") -> None:
        path = PROFILE_PATH
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = self.model_dump(
                mode="json",
                context={"encryption_enabled": self.encryption_enabled},
            )
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
            self.notifier.changed.emit(reason)
        except Exception as e:
            logger.error(f"保存档案失败: {e}")

    @classmethod
    def load(cls) -> Profile:
        path = PROFILE_PATH

        if not path.exists():
            profile = cls()
            profile.save()
            return profile

        try:
            raw = cls._load_raw_payload(path)
            assert raw.get("schema_version", -1) == _PROFILE_SCHEMA_VERSION
            return cls(**raw)
        except AssertionError as e:
            logger.warning(f"档案版本不兼容, 按新结构强制重建: {e}")
            rebuilt = cls()
            rebuilt.save()
            return rebuilt
        except Exception as e:
            raise RuntimeError(f"档案文件 {path} 解析失败") from e

    def _find_automation_index(self, automation_id: str) -> int:
        for i, item in enumerate(self.automations):
            if automation_id is not None and item.id == automation_id:
                return i
        return -1

    def list_automation(self) -> list[BaseAutomation]:
        return cast(list[BaseAutomation], self.automations.copy())

    def get_automation(self, id: str) -> BaseAutomation | None:
        for item in self.automations:
            if item.id == id:
                return item
        return None

    def upsert_automation(self, automation: BaseAutomation) -> None:
        i = self._find_automation_index(automation.id)
        if i != -1:
            self.automations[i] = cast(Automation, automation)
            return
        self.automations.append(cast(Automation, automation))

    def delete_automation(self, automation_id: str) -> bool:
        i = self._find_automation_index(automation_id)
        if i == -1:
            return False
        del self.automations[i]
        return True


profile = Profile.load()
