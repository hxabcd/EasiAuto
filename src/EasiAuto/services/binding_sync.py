from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from loguru import logger
from pydantic import BaseModel

from EasiAuto.integrations.classisland_manager import (
    CiSubject,
    ManagedCiAutomation,
)
from EasiAuto.integrations.classisland_manager import (
    classisland_manager as ci_manager,
)
from EasiAuto.models.config import config
from EasiAuto.models.profile import EasiAutomation, profile


class SubjectRef(BaseModel):
    """通用科目标识"""

    name: str
    provider: str
    id: str | None = None


@dataclass(slots=True)
class SyncContext:
    subjects: dict[str, CiSubject]
    managed_by_subject: dict[str, ManagedCiAutomation]
    used_guids: set[str]


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


class ClassIslandBindingBackend(BindingSyncBackendBase):
    """ClassIsland 绑定同步后端实现"""

    provider = "classisland"

    def __init__(self) -> None:
        super().__init__()

    def list_subjects(self, reload: bool = False) -> list[SubjectRef]:
        """列出 ClassIsland 中的所有科目"""

        if not ci_manager:
            return []

        if reload:
            ci_manager.reload()

        return [SubjectRef(name=item.name, provider=self.provider, id=item.id) for item in ci_manager.get_subjects()]

    def get_binding_map(self, reload: bool = False) -> dict[str, str]:
        """读取当前绑定关系（subject_id -> automation_id）"""
        if not ci_manager:
            return {}

        if reload:
            ci_manager.reload()

        bindings: dict[str, str] = {}
        for item in ci_manager.get_automations():
            automation_id = item.id
            if not item.subject_id or not automation_id:
                continue
            if item.subject_id in bindings:
                # NOTE: 当前重复科目冲突仅保留首条，后续可扩展显式冲突处理策略。
                continue
            bindings[item.subject_id] = automation_id
        return bindings

    def sync(self, binding_map: Mapping[str, str | None]) -> bool:
        """执行与 ClassIsland 的同步操作
        Args:
            binding_map: 目标绑定关系 (subject_id -> automation_id)
        """
        errors: list[str] = []

        if not ci_manager:
            errors.append("ClassIsland 管理器未初始化")
            return self._set_errors(errors)

        ci_manager.reload()
        context = self._prepare_context()

        resolved_bindings = self._resolve_bindings(binding_map, context)
        automations = self._build_automations(resolved_bindings, context)
        ok = ci_manager.save_automations(automations)

        if not ok:
            errors.append("保存 ClassIsland 自动化配置失败")

        return self._set_errors(errors)

    def _prepare_context(self) -> SyncContext:
        """重载配置并建立索引, 准备上下文"""
        automations = list(ci_manager.get_automations())
        subjects = {item.id: item for item in ci_manager.get_subjects()}

        managed_by_subject: dict[str, ManagedCiAutomation] = {}
        for item in automations:
            managed_by_subject.setdefault(item.subject_id, item)

        return SyncContext(
            subjects=subjects,
            managed_by_subject=managed_by_subject,
            used_guids=set(),
        )

    def _resolve_bindings(
        self, binding_map: Mapping[str, str | None], context: SyncContext
    ) -> list[tuple[CiSubject, EasiAutomation]]:
        normalized: list[tuple[CiSubject, EasiAutomation]] = []
        for subject_id, automation_id in binding_map.items():
            if not subject_id or not automation_id:
                continue
            subject = context.subjects.get(subject_id)
            automation = profile.get_automation(automation_id)
            if subject is None or automation is None:
                continue
            normalized.append((subject, automation))
        return normalized

    def _build_automations(
        self,
        bindings: list[tuple[CiSubject, EasiAutomation]],
        context: SyncContext,
    ) -> list[ManagedCiAutomation]:
        """根据目标绑定生成最终自动化列表"""
        output: list[ManagedCiAutomation] = []

        for subject, automation in bindings:
            # 尽可能复用已有数据
            existing = self._resolve_existing(subject.id, context)
            name = existing.name if existing else automation.get_automation_name(subject_name=subject.name)
            guid = existing.guid if existing else str(uuid.uuid4())
            pretime = existing.pretime if existing else config.ClassIsland.DefaultPreTime
            context.used_guids.add(guid)

            output.append(
                ManagedCiAutomation(
                    guid=guid,
                    name=name,
                    is_enabled=automation.enabled,
                    subject_id=subject.id,
                    pretime=pretime,
                    args=f"login --id {automation.id}",
                )
            )

        return output

    def _resolve_existing(
        self,
        subject_id: str,
        context: SyncContext,
    ) -> ManagedCiAutomation | None:
        """根据 subject_id 查找可复用的现有自动化"""
        subject_existing = context.managed_by_subject.get(subject_id)
        if subject_existing and subject_existing.guid not in context.used_guids:
            return subject_existing

        return None
