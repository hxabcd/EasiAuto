from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from cryptography.fernet import InvalidToken
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from EasiAuto.common.consts import PROFILE_PATH
from EasiAuto.common.secret_store import get_profile_cipher

_PASSWORD_TOKEN_PREFIX = "ea1$"


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

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="唯一ID")
    account: str
    password: str
    name: str | None = Field(default=None, description="名称")
    account_name: str | None = Field(default=None, description="希沃白板用户名")
    avatar: Any = Field(default=None, description="希沃白板头像")
    enabled: bool = Field(default=True, description="是否启用")


class Profile(BaseModel):
    """档案模型"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    encryption_enabled: bool = Field(default=True, description="是否启用档案密码加密")
    automations: list[EasiAutomation] = Field(default_factory=list)

    def save(self, file: str | Path) -> None:
        path = Path(file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
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
            loaded = cls(**raw)
            for item in loaded.automations:
                try:
                    item.password = decrypt_password(item.password)
                except Exception as e:
                    logger.error(f"解密账号 {item.account} 的密码失败，已清空密码: {e}")
                    item.password = ""
            return loaded
        except Exception as e:
            logger.error(f"档案文件解析失败，使用空档案: {e}")
            return cls()

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
                del self.automations[idx]
                return True
        return False

    def delete_by_id(self, automation_id: str) -> bool:
        for idx, item in enumerate(self.automations):
            if item.id == automation_id:
                del self.automations[idx]
                return True
        return False


profile = Profile.load(PROFILE_PATH)
