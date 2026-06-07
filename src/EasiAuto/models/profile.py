from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal

from cryptography.fernet import InvalidToken
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, model_serializer

from PySide6.QtCore import QObject, Signal

from EasiAuto.consts import EA_PREFIX, PROFILE_PATH
from EasiAuto.core.security import get_profile_cipher
from EasiAuto.models.config import config

_PROFILE_SCHEMA_VERSION = 2
_PASSWORD_TOKEN_PREFIX = f"ea{_PROFILE_SCHEMA_VERSION}$"


ProfileChangeReason = Literal[
    "profile_changed",
    "automation_saved",
    "automation_deleted",
    "encryption_changed",
]

class ProfileNotifier(QObject):
    changed = Signal(str)


def encrypt_password(plaintext: str) -> str:
    if plaintext == "":
        return plaintext

    cipher = get_profile_cipher()
    token = cipher.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_PASSWORD_TOKEN_PREFIX}{token}"


def decrypt_password(token: str) -> str:
    if token == "" or not token.startswith(_PASSWORD_TOKEN_PREFIX):
        return token

    cipher = get_profile_cipher()
    raw = token.removeprefix(_PASSWORD_TOKEN_PREFIX)
    try:
        return cipher.decrypt(raw.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("密码密文校验失败或密钥不可用") from e


class EasiAutomation(BaseModel):
    """单条自动登录档案（账密类型）"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    account: str = Field(default="")
    password: str = Field(default="")
    name: str | None = Field(default=None, description="自动化名称/老师名称")
    account_name: str | None = Field(default=None, description="希沃白板用户名")
    avatar: Any = Field(default=None, description="希沃白板头像")
    enabled: bool = Field(default=True, description="是否启用")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def _automation_type(self) -> str:
        return "password"

    @model_serializer(mode="wrap")
    def check_on_dump(self, serializer):
        if self.is_qrcode_profile:
            return serializer(self)
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

    def get_automation_name(self, subject_name: str | None) -> str:
        text = f"{EA_PREFIX} {config.ClassIsland.DefaultDisplayName}"
        if subject_name and self.name:
            text += f" - {subject_name} ({self.name})"
        elif t := (subject_name or self.display_name):
            text += f" - {t}"
        return text

    @property
    def export_name(self) -> str:
        label = self.name or self.account
        return f"希沃自动登录（{label}）"

    @property
    def is_qrcode_profile(self) -> bool:
        return False


class QrcodeAutomation(EasiAutomation):
    """二维码登录档案"""

    token: str = Field(default="", description="二维码登录令牌")
    user_id: str | None = Field(default=None, description="希沃用户 ID")
    nick_name: str | None = Field(default=None, description="希沃用户昵称")
    phone: str | None = Field(default=None, description="希沃用户手机号")

    @property
    def _automation_type(self) -> str:
        return "qrcode"

    @model_serializer(mode="wrap")
    def check_on_dump(self, serializer):
        if not self.token.strip():
            raise ValueError("令牌不能为空")
        return serializer(self)

    @property
    def detail_name(self) -> str | None:
        return "二维码档案"

    @property
    def is_qrcode_profile(self) -> bool:
        return True


class Profile(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_version: int = Field(default=_PROFILE_SCHEMA_VERSION)
    encryption_enabled: bool = Field(default=True, description="是否启用档案密码加密")

    automations: list[EasiAutomation] = Field(default_factory=list)
    notifier: ProfileNotifier = Field(default_factory=ProfileNotifier, exclude=True)

    # 存储

    def _dump_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        if not self.encryption_enabled:
            return payload
        for item in payload["automations"]:
            is_qr = bool(item.get("token"))
            item["type"] = "qrcode" if is_qr else "password"
            if is_qr:
                item["token"] = encrypt_password(item["token"])
            else:
                item["password"] = encrypt_password(item["password"])
        return payload

    @classmethod
    def _load_raw_payload(cls, path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def _decrypt_automation_passwords(self) -> None:
        for item in self.automations:
            if isinstance(item, QrcodeAutomation):
                try:
                    item.token = decrypt_password(item.token)
                except Exception as e:
                    logger.error(f"解密令牌失败: {e}")
                    item.token = ""
            else:
                try:
                    item.password = decrypt_password(item.password)
                except Exception as e:
                    logger.error(f"解密密码失败: {e}")
                    item.password = ""

    def save(self, reason: ProfileChangeReason = "profile_changed") -> None:
        path = PROFILE_PATH

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._dump_payload()
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

            raw_automations = raw.pop("automations", [])
            loaded = cls(**raw)
            for item_data in raw_automations:
                auto_type = item_data.pop("type", None)
                if auto_type == "qrcode" or item_data.get("token"):
                    loaded.automations.append(QrcodeAutomation(**item_data))
                else:
                    loaded.automations.append(EasiAutomation(**item_data))
            loaded._decrypt_automation_passwords()
            return loaded
        except AssertionError as e:
            logger.warning(f"档案版本不兼容, 按新结构强制重建: {e}")
            rebuilt = cls()
            rebuilt.save()
            return rebuilt
        except Exception as e:
            raise RuntimeError(f"档案文件 {path} 解析失败") from e

    # 自动登录档案管理

    def _find_automation_index(self, automation_id: str) -> int:
        for i, item in enumerate(self.automations):
            if automation_id is not None and item.id == automation_id:
                return i
        return -1

    def list_automations(self) -> list[EasiAutomation]:
        return self.automations.copy()

    def get_automation(self, id: str) -> EasiAutomation | None:
        for item in self.automations:
            if item.id == id:
                return item
        return None

    def upsert_automation(self, automation: EasiAutomation) -> None:
        i = self._find_automation_index(automation.id)
        if i != -1:
            self.automations[i] = automation
            return
        self.automations.append(automation)

    def delete_automation(self, automation_id: str) -> bool:
        i = self._find_automation_index(automation_id)
        if i == -1:
            return False
        del self.automations[i]
        return True


profile = Profile.load()
