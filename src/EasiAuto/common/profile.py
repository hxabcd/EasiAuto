from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from cryptography.fernet import InvalidToken
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from EasiAuto.common.config import config
from EasiAuto.common.consts import EA_PREFIX, PROFILE_PATH
from EasiAuto.common.secret_store import get_profile_cipher

_PROFILE_SCHEMA_VERSION = 1
_PASSWORD_TOKEN_PREFIX = f"ea{_PROFILE_SCHEMA_VERSION}$"


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
    """单条自动登录档案"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    account: str
    password: str
    name: str | None = Field(default=None, description="自动化名称/老师名称")
    account_name: str | None = Field(default=None, description="希沃白板用户名")
    avatar: Any = Field(default=None, description="希沃白板头像")
    enabled: bool = Field(default=True, description="是否启用")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def display_name(self) -> str | None:
        return self.name or self.account_name

    @property
    def detail_name(self) -> str | None:
        if not self.account:
            return None
        return self.account

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


class SubjectRef(BaseModel):
    """可跨执行器的科目标识"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    provider: str = Field(description="来源提供方，如 classisland")
    external_id: str | None = Field(default=None, description="外部系统科目ID")
    name: str = Field(description="科目显示名")


class SubjectBinding(BaseModel):
    """科目到档案的单向绑定"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    subject: SubjectRef
    profile_id: str
    managed_guid: str | None = Field(default=None, description="同步后对应的自动化 GUID")


class Profile(BaseModel):
    """档案模型"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_version: int = Field(default=_PROFILE_SCHEMA_VERSION)
    encryption_enabled: bool = Field(default=True, description="是否启用档案密码加密")
    automations: list[EasiAutomation] = Field(default_factory=list)
    subject_bindings: list[SubjectBinding] = Field(default_factory=list)

    def cleanup_invalid_bindings(self, provider: str | None = None) -> int:
        """清理指向不存在档案的关联关系，返回清理数量。"""
        valid_profile_ids = {item.id for item in self.automations}
        before = len(self.subject_bindings)

        if provider is None:
            self.subject_bindings = [item for item in self.subject_bindings if item.profile_id in valid_profile_ids]
        else:
            self.subject_bindings = [
                item
                for item in self.subject_bindings
                if item.subject.provider != provider or item.profile_id in valid_profile_ids
            ]

        return before - len(self.subject_bindings)

    def save(self, file: str | Path) -> None:
        path = Path(file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            removed = self.cleanup_invalid_bindings()
            if removed:
                logger.warning(f"保存前自动清理了 {removed} 条失效关联")
            payload = self.model_dump(mode="json")
            if self.encryption_enabled:
                for item in payload["automations"]:
                    item["password"] = encrypt_password(item["password"])
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"保存档案失败: {e}")

    @classmethod
    def load(cls, file: str | Path) -> Profile:
        path = Path(file)
        if not path.exists():
            profile = cls()
            profile.save(path)
            logger.info(f"档案文件 {path} 不存在，自动生成")
            return profile

        try:
            with path.open(encoding="utf-8") as f:
                raw = json.load(f)
            if raw.get("schema_version") != _PROFILE_SCHEMA_VERSION:
                raise RuntimeError("档案版本不兼容")

            loaded = cls(**raw)
            for item in loaded.automations:
                try:
                    item.password = decrypt_password(item.password)
                except Exception as e:
                    logger.error(f"解密账号 {item.account} 的密码失败，已清空密码: {e}")
                    item.password = ""
            removed = loaded.cleanup_invalid_bindings()
            if removed:
                logger.warning(f"检测到 {removed} 条失效关联，已自动清理并写回")
                loaded.save(path)
            return loaded
        except Exception as e:
            logger.error(f"档案文件解析失败，按新结构强制重建: {e}")
            rebuilt = cls()
            rebuilt.save(path)
            return rebuilt

    def list_automations(self) -> list[EasiAutomation]:
        return list(self.automations)

    def get_by_account(self, account: str) -> EasiAutomation | None:
        for item in self.automations:
            if item.account == account:
                return item
        return None

    def get_by_id(self, automation_id: str) -> EasiAutomation | None:
        for item in self.automations:
            if item.id == automation_id:
                return item
        return None

    def upsert(self, automation: EasiAutomation) -> None:
        for idx, item in enumerate(self.automations):
            if item.id == automation.id:
                self.automations[idx] = automation
                return
            if item.account == automation.account:
                self.automations[idx] = automation
                return
        self.automations.append(automation)

    def delete_by_account(self, account: str) -> bool:
        for idx, item in enumerate(self.automations):
            if item.account == account:
                self.clear_bindings_for_profile(item.id)
                del self.automations[idx]
                return True
        return False

    def delete_by_id(self, automation_id: str) -> bool:
        for idx, item in enumerate(self.automations):
            if item.id == automation_id:
                self.clear_bindings_for_profile(item.id)
                del self.automations[idx]
                return True
        return False

    @staticmethod
    def _same_name(left: str, right: str) -> bool:
        return left.strip().lower() == right.strip().lower()

    def _find_binding_index(self, provider: str, external_id: str | None, name: str | None) -> int:
        if external_id:
            for idx, item in enumerate(self.subject_bindings):
                if item.subject.provider == provider and item.subject.external_id == external_id:
                    return idx

        if name:
            for idx, item in enumerate(self.subject_bindings):
                if item.subject.provider != provider:
                    continue
                if self._same_name(item.subject.name, name):
                    return idx

        return -1

    def list_bindings(self, provider: str | None = None) -> list[SubjectBinding]:
        if provider is None:
            return list(self.subject_bindings)
        return [item for item in self.subject_bindings if item.subject.provider == provider]

    def get_binding(self, provider: str, external_id: str | None, name: str | None) -> SubjectBinding | None:
        idx = self._find_binding_index(provider=provider, external_id=external_id, name=name)
        if idx == -1:
            return None
        return self.subject_bindings[idx]

    def get_profile_id_by_subject(self, provider: str, external_id: str | None, name: str | None) -> str | None:
        binding = self.get_binding(provider=provider, external_id=external_id, name=name)
        return binding.profile_id if binding else None

    def get_subjects_by_profile(self, profile_id: str, provider: str | None = None) -> list[SubjectRef]:
        matched = [item.subject for item in self.subject_bindings if item.profile_id == profile_id]
        if provider is None:
            return matched
        return [item for item in matched if item.provider == provider]

    def set_binding(
        self,
        subject: SubjectRef,
        profile_id: str | None,
        managed_guid: str | None = None,
    ) -> None:
        idx = self._find_binding_index(
            provider=subject.provider,
            external_id=subject.external_id,
            name=subject.name,
        )

        if not profile_id:
            if idx != -1:
                del self.subject_bindings[idx]
            return

        if idx == -1:
            self.subject_bindings.append(
                SubjectBinding(
                    subject=subject,
                    profile_id=profile_id,
                    managed_guid=managed_guid,
                )
            )
            return

        existing = self.subject_bindings[idx]
        existing.subject = subject
        existing.profile_id = profile_id
        if managed_guid is not None:
            existing.managed_guid = managed_guid

    def clear_bindings(self, provider: str | None = None) -> None:
        if provider is None:
            self.subject_bindings.clear()
            return
        self.subject_bindings = [item for item in self.subject_bindings if item.subject.provider != provider]

    def clear_bindings_for_profile(self, profile_id: str, provider: str | None = None) -> None:
        if provider is None:
            self.subject_bindings = [item for item in self.subject_bindings if item.profile_id != profile_id]
            return
        self.subject_bindings = [
            item
            for item in self.subject_bindings
            if not (item.profile_id == profile_id and item.subject.provider == provider)
        ]

    def update_managed_guid(self, provider: str, external_id: str | None, name: str | None, guid: str | None) -> None:
        idx = self._find_binding_index(provider=provider, external_id=external_id, name=name)
        if idx == -1:
            return
        self.subject_bindings[idx].managed_guid = guid


profile = Profile.load(PROFILE_PATH)
