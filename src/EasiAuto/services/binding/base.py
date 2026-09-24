"""绑定同步的通用契约（与具体外部软件无关）

新增平台支持时，继承 :class:`BindingSyncBackendBase` 实现一个新后端模块即可。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from loguru import logger
from pydantic import BaseModel


class SubjectRef(BaseModel):
    """通用科目标识"""

    name: str
    provider: str
    id: str | None = None


class BindingSyncBackendBase(ABC):
    provider: str

    def __init__(self) -> None:
        self.last_errors: list[str] = []

    @abstractmethod
    def list_subjects(self) -> list[SubjectRef]:
        raise NotImplementedError

    @abstractmethod
    def get_binding_map(self) -> dict[str, str]:
        """读取当前绑定关系 (subject_id -> automation_id)"""
        raise NotImplementedError

    @abstractmethod
    def sync(self, binding_map: Mapping[str, str | None]) -> bool:
        raise NotImplementedError

    def _set_errors(self, errors: list[str]) -> bool:
        self.last_errors = errors.copy()
        if errors:
            logger.warning(f"绑定同步失败: {'；'.join(errors)}")
            return False
        return True
