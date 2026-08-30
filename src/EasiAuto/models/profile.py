from __future__ import annotations

import base64
import json
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal, cast

from cryptography.fernet import Fernet, InvalidToken
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
from EasiAuto.core import security
from EasiAuto.core.security import get_profile_cipher
from EasiAuto.models.config import config

_PROFILE_SCHEMA_VERSION = 3
_SECRET_TOKEN_PREFIX = "ea$"
# 主密码校验密文中保存的固定负载，仅用于验证用户输入的主密码是否正确
_MASTER_PASSWORD_CHECK_PAYLOAD = "EasiAuto-profile-master-check"

ProfileChangeReason = Literal[
    "profile_changed",
    "automation_saved",
    "automation_deleted",
    "encryption_changed",
]


class ProfileLockedError(RuntimeError):
    """档案已加密但会话未解锁时尝试保存所抛出的异常。"""


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


def _serialize_secret_field(value: str, info: SerializationInfo) -> str:
    """按加密开关序列化敏感字段（密码/账号）。"""
    if info.context and info.context.get("encryption_enabled"):
        return encrypt_secret(value)
    return value


def _deserialize_secret_field(value: str, label: str) -> str:
    """反序列化敏感字段；未解锁时静默返回空串，解锁后由 reload 刷新明文。"""
    try:
        return decrypt_secret(value)
    except Exception as e:
        if security.is_master_key_unlocked():
            logger.error(f"解密{label}失败: {e}")
        return ""


def _verify_master_password(master_password: str, salt_b64: str, check_token: str) -> bool:
    """校验主密码是否正确：用主密码派生密钥解密校验密文。"""
    try:
        salt = base64.b64decode(salt_b64)
        cipher = Fernet(security.derive_master_key(master_password, salt))
        payload = cipher.decrypt(check_token.removeprefix(_SECRET_TOKEN_PREFIX).encode("ascii"))
        return payload == _MASTER_PASSWORD_CHECK_PAYLOAD.encode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return False


def _is_legacy_encryption(raw: dict[str, Any]) -> bool:
    """判断是否为旧版机器密钥加密档案（加密开启但没有主密码元数据）。"""
    return bool(raw.get("encryption_enabled")) and not raw.get("encryption_check")


def _normalize_profile_format(raw: dict[str, Any]) -> bool:
    """粗暴归一化 1.2.1 及中间测试版的档案为 schema 3 明文存档。

    统一处理两种旧格式：``schema_version < 3``（仍是 v1.2.1，令牌前缀为 ``ea2$``）
    以及 ``schema_version == 3`` 但用旧机器密钥加密的档案。
    做法：把 ``ea2$`` / ``ea$`` 令牌用旧密钥解密为明文，并关闭加密。
    旧密钥文件缺失或解密失败时，对应密码置空（交由用户重新填写）。

    Returns
    -------
    是否完全成功（没有密码解密失败）。失败时由调用方备份原文件。
    """
    legacy_cipher = security.get_legacy_cipher()
    success = True
    for item in raw.get("automations", []):
        if "type" not in item:
            item["type"] = "password"
        token = item.get("password") or ""
        raw_token = token.replace("ea2$", "ea$", 1)
        if not raw_token.startswith(_SECRET_TOKEN_PREFIX):
            continue
        if legacy_cipher is None:
            item["password"] = ""
            success = False
            continue
        try:
            item["password"] = legacy_cipher.decrypt(
                raw_token.removeprefix(_SECRET_TOKEN_PREFIX).encode("ascii")
            ).decode("utf-8")
        except InvalidToken as e:
            logger.error(f"旧档案密码解密失败，已置空: {e}")
            item["password"] = ""
            success = False
    raw["encryption_enabled"] = False
    raw.pop("encryption_salt", None)
    raw.pop("encryption_check", None)
    return success


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
    def export_name(self) -> str:
        label = self.name or self.account
        return f"希沃自动登录（{label}）"

    @field_serializer("password", mode="plain")
    def _ser_password(self, value: str, _info: SerializationInfo) -> str:
        return _serialize_secret_field(value, _info)

    @field_validator("password", mode="after")
    @classmethod
    def _deser_password(cls, value: str) -> str:
        return _deserialize_secret_field(value, "密码")

    @field_serializer("account", mode="plain")
    def _ser_account(self, value: str, _info: SerializationInfo) -> str:
        return _serialize_secret_field(value, _info)

    @field_validator("account", mode="after")
    @classmethod
    def _deser_account(cls, value: str) -> str:
        return _deserialize_secret_field(value, "账号")


Automation = EasiAutomation


class Profile(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_version: int = Field(default=_PROFILE_SCHEMA_VERSION)
    encryption_enabled: bool = Field(default=False, description="是否使用主密码加密档案（默认禁用）")
    encryption_salt: str | None = Field(default=None, description="主密码盐值（base64）")
    encryption_check: str | None = Field(default=None, description="主密码校验密文")
    passwordless_view: bool = Field(default=True, description="是否允许在本机免密打开档案页查看密码")

    automations: list[Automation] = Field(default_factory=list)
    notifier: ProfileNotifier = Field(default_factory=ProfileNotifier, exclude=True)

    @classmethod
    def _load_raw_payload(cls, path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def save(self, reason: ProfileChangeReason = "profile_changed") -> None:
        path = PROFILE_PATH
        if self.encryption_enabled and not security.is_master_key_unlocked():
            raise ProfileLockedError("档案已加密但主密码未解锁，拒绝保存以避免数据损坏")
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

    def enable_encryption(self, master_password: str) -> None:
        """启用主密码加密：生成盐值、派生密钥并加密保存全部档案。

        无论是否免密查看，都会把派生密钥写入本机缓存（用于自动登录）。
        「免密查看档案」作为独立设置项，默认开启。
        """
        salt = os.urandom(16)
        security.unlock_master_key(master_password, salt)
        security.cache_master_key(cast(bytes, security.get_master_key()))
        self.passwordless_view = True
        self.encryption_salt = base64.b64encode(salt).decode("ascii")
        self.encryption_check = encrypt_secret(_MASTER_PASSWORD_CHECK_PAYLOAD)
        self.encryption_enabled = True
        self.save(reason="encryption_changed")

    def disable_encryption(self, master_password: str) -> bool:
        """校验主密码并关闭加密（档案恢复明文保存）；密码错误返回 False。"""
        if not self.encryption_salt or not self.encryption_check:
            return False
        if not _verify_master_password(master_password, self.encryption_salt, self.encryption_check):
            return False
        security.unlock_master_key(master_password, base64.b64decode(self.encryption_salt))
        # 重新载入明文密码，避免在锁定态加载的空值被写回磁盘造成数据丢失
        self.reload()
        self.encryption_enabled = False
        self.encryption_salt = None
        self.encryption_check = None
        self.save(reason="encryption_changed")
        security.lock_master_key()
        security.clear_cached_key()
        return True

    def unlock_master_password(self, master_password: str) -> bool:
        """校验主密码并解锁当前会话；成功后载入明文密码，并把密钥写入本机缓存（用于自动登录）。"""
        if not self.encryption_salt or not self.encryption_check:
            return False
        if not _verify_master_password(master_password, self.encryption_salt, self.encryption_check):
            return False
        security.unlock_master_key(master_password, base64.b64decode(self.encryption_salt))
        security.cache_master_key(cast(bytes, security.get_master_key()))
        self.reload()
        return True

    def read_cached_unlock(self) -> bool:
        """尝试用本机缓存自动解锁当前会话；仅当缓存密钥与档案校验密文匹配时才接受。"""
        key = security.read_cached_key()
        if key is None:
            return False
        if not self._cached_key_valid(key):
            security.clear_cached_key()
            return False
        security.set_master_key(key)
        self.reload()
        return True

    def _cached_key_valid(self, key: bytes) -> bool:
        """用档案内的主密码校验密文验证缓存密钥是否匹配当前主密码。"""
        if not self.encryption_check:
            return False
        try:
            payload = Fernet(key).decrypt(self.encryption_check.removeprefix(_SECRET_TOKEN_PREFIX).encode("ascii"))
            return payload == _MASTER_PASSWORD_CHECK_PAYLOAD.encode("utf-8")
        except (InvalidToken, ValueError):
            return False

    def reload(self) -> None:
        """重新从磁盘载入档案并保持单例引用（解锁主密码后刷新明文密码）。"""
        fresh = Profile.load()
        for name in self.model_fields:
            if name == "notifier":
                continue
            setattr(self, name, getattr(fresh, name))
        self.notifier.changed.emit("encryption_changed")

    @classmethod
    def load(cls) -> Profile:
        path = PROFILE_PATH

        if not path.exists():
            profile = cls()
            profile.save()
            return profile

        try:
            raw = cls._load_raw_payload(path)
            schema_version = raw.get("schema_version", -1)
            if not isinstance(schema_version, int) or schema_version < 2:
                logger.warning("强制重建档案")
                rebuilt = cls()
                rebuilt.save()
                return rebuilt

            # 旧版（v1.2.1 正式版 / 中间测试版）或旧机器密钥加密档案：归一化为明文存档
            if schema_version < 3 or _is_legacy_encryption(raw):
                logger.warning("归一化旧档案格式：机器密钥加密改为主密码加密，默认禁用加密")
                success = _normalize_profile_format(raw)
                raw["schema_version"] = 3
                upgraded = cls(**raw)
                if success:
                    upgraded.save()
                else:
                    cls._backup_original_profile()
                    logger.error("旧档案部分密码解密失败，已备份原文件至 .bak，请重新填写对应密码后保存")
                return upgraded
            return cls(**raw)

        except Exception as e:
            raise RuntimeError(f"档案文件 {path} 解析失败") from e

    @staticmethod
    def _backup_original_profile() -> None:
        """把尚未迁移的原始档案备份为 ``profile.json.bak``（迁移失败时保留）。"""
        src = PROFILE_PATH
        dst = src.with_name(src.name + ".bak")
        try:
            dst.write_bytes(src.read_bytes())
        except OSError as e:
            logger.error(f"备份原始档案失败: {e}")

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
