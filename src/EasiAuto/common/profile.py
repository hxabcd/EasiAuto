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

_PROFILE_SCHEMA_VERSION = 2
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
    """通用科目标识"""

    name: str
    provider: str
    id: str | None = None  # 该科目对应的外部科目 id


class BindingItem(BaseModel):
    """SubjectRef -> EasiAutomation 单向绑定"""

    subject: SubjectRef
    automation_id: str
    id: str | None = None  # 该绑定对应的外部自动化 id


class Profile(BaseModel):
    schema_version: int = Field(default=_PROFILE_SCHEMA_VERSION)
    encryption_enabled: bool = Field(default=True, description="是否启用档案密码加密")

    automations: list[EasiAutomation] = Field(default_factory=list)
    bindings: list[BindingItem] = Field(default_factory=list)

    # 存储

    def _dump_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        if not self.encryption_enabled:
            return payload
        for item in payload["automations"]:
            item["password"] = encrypt_password(item["password"])
        return payload

    @classmethod
    def _load_raw_payload(cls, path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def _decrypt_automation_passwords(self) -> None:
        for item in self.automations:
            try:
                item.password = decrypt_password(item.password)
            except Exception as e:
                logger.error(f"解密账号 {item.account} 的密码失败, 已清空密码: {e}")
                item.password = ""

    def cleanup_invalid_bindings(self) -> int:
        """清理指向无效自动登录档案的关联"""
        valid_profile_ids = {item.id for item in self.automations}
        before = len(self.bindings)
        self.bindings = [item for item in self.bindings if item.automation_id in valid_profile_ids]

        removed = before - len(self.bindings)
        if removed > 0:
            logger.warning(f"清理了 {removed} 条无效关联")
        return removed

    def save(self) -> None:
        path = PROFILE_PATH

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.cleanup_invalid_bindings()
            payload = self._dump_payload()
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
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

            loaded = cls(**raw)
            loaded._decrypt_automation_passwords()
            loaded.cleanup_invalid_bindings()
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
        self._clear_bindings_for_automation(self.automations[i].id)
        del self.automations[i]
        return True

    # 绑定管理

    def _find_binding_index(self, subject: SubjectRef) -> int:
        if subject.id:
            for i, item in enumerate(self.bindings):
                if item.subject.id == subject.id:
                    return i

        # 若无法通过 id 寻找科目，回退到名称查找
        for i, item in enumerate(self.bindings):
            if item.subject.name == subject.name:
                return i

        return -1

    def list_bindings(self) -> list[BindingItem]:
        return self.bindings.copy()

    def get_automation_id_by_subject(self, subject: SubjectRef) -> str | None:
        i = self._find_binding_index(subject)
        if i == -1:
            return None
        binding = self.bindings[i]

        return binding.automation_id if binding else None

    def get_subjects_by_automation(self, automation_id: str) -> list[SubjectRef]:
        return [item.subject for item in self.bindings if item.automation_id == automation_id]

    def set_binding(self, subject: SubjectRef, automation_id: str | None, id: str | None = None) -> None:
        i = self._find_binding_index(subject)

        if not automation_id:  # 移除
            if i != -1:
                del self.bindings[i]
            return

        if i != -1:  # 修改
            existing = self.bindings[i]
            existing.subject = subject
            existing.automation_id = automation_id
            if id is not None:
                existing.id = id
        else:  # 创建
            self.bindings.append(BindingItem(subject=subject, automation_id=automation_id, id=id))

    def clear_bindings(self) -> None:
        self.bindings.clear()

    def _clear_bindings_for_automation(self, profile_id: str) -> None:
        self.bindings = [item for item in self.bindings if item.automation_id != profile_id]


profile = Profile.load()
