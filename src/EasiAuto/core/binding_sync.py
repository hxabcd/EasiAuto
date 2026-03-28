from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from EasiAuto.common.config import config
from EasiAuto.common.consts import EA_EXECUTABLE, EA_PREFIX
from EasiAuto.common.profile import BindingItem, EasiAutomation, Profile, SubjectRef
from EasiAuto.integrations.classisland_manager import CiSubject
from EasiAuto.integrations.classisland_manager import classisland_manager as ci_manager

_ARG_PATTERN = r"(?:{flag1}|{flag2})\s+(\"[^\"]+\"|\S+)"


def _clean_arg(raw: str | None) -> str | None:
    if raw is None:
        return None
    return raw.strip().strip('"')


def _extract_arg(args: str, short_flag: str, long_flag: str) -> str | None:
    """从命令参数中提取指定标志的值"""
    pattern = _ARG_PATTERN.format(flag1=re.escape(short_flag), flag2=re.escape(long_flag))
    match = re.search(pattern, args)
    if not match:
        return None
    return _clean_arg(match.group(1))



@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    migrated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


class BindingSyncBackendBase(ABC):
    provider: str

    @abstractmethod
    def list_subjects(self) -> list[SubjectRef]:
        raise NotImplementedError

    @abstractmethod
    def sync(self, profile_data: Profile) -> SyncResult:
        raise NotImplementedError


class ClassIslandBindingBackend(BindingSyncBackendBase):
    """ClassIsland 绑定同步后端实现"""

    provider = "classisland"

    def list_subjects(self) -> list[SubjectRef]:
        """列出 ClassIsland 中的所有科目"""
        if not ci_manager:
            return []

        with self._suppress_reload_error():
            ci_manager.reload_config()

        subjects: list[SubjectRef] = []
        for subject in ci_manager.list_subjects():
            subjects.append(
                SubjectRef(
                    name=subject.name,
                    provider=self.provider,
                    id=subject.id,
                )
            )
        return subjects

    def sync(self, profile_data: Profile) -> SyncResult:
        """执行与 ClassIsland 的同步操作

        1. 读取当前绑定与档案并校验（档案存在、启用、密码非空）
        2. 将先前基于明文账号密码的自动化迁移
        3. 计算期望状态（每个已绑定科目 1 条自动化）与当前 managed 状态的差异
        4. 按差异执行 create/update/delete
        """
        result = SyncResult()

        if not ci_manager:
            result.errors.append("ClassIsland 管理器未初始化")
            return result

        with self._suppress_reload_error(result):
            ci_manager.reload_config()

        # 构建科目映射和期望的绑定关系
        subject_map: dict[str, CiSubject] = {item.id: item for item in ci_manager.list_subjects()}
        all_bindings = profile_data.list_bindings()
        desired = self._build_desired_bindings(profile_data, all_bindings, subject_map, result)

        # 处理现有自动化配置
        automations = list(ci_manager.ci_automations)
        guid_to_automation = {guid: auto for auto in automations if (guid := self._get_guid(auto))}
        tracked_guids = {item.id for item in all_bindings if item.id}

        # 确定受管理的自动化配置
        managed_guids = {
            guid
            for guid, automation in guid_to_automation.items()
            if self._is_managed_automation(automation, tracked_guids)
        }

        replacement_guids: set[str] = set()
        desired_entries: list[tuple[str, dict, BindingItem]] = []
        reused_guids: set[str] = set()

        # 处理每个绑定关系
        for subject_id, (binding, profile_auto, subject) in desired.items():
            existing = None
            migrated = False

            # 查找现有自动化配置
            if binding.id and binding.id in guid_to_automation:
                existing = guid_to_automation[binding.id]
            if existing is None:
                existing = self._find_managed_by_subject(
                    guid_to_automation=guid_to_automation,
                    managed_guids=managed_guids,
                    subject_id=subject_id,
                    exclude=replacement_guids,
                )
            if existing is None:
                existing = self._find_legacy_candidate(
                    automations=automations,
                    subject_id=subject_id,
                    account=profile_auto.account,
                    password=profile_auto.password,
                    exclude=replacement_guids,
                )
                migrated = existing is not None

            # 创建或更新自动化配置
            if existing is None:
                guid = str(uuid.uuid4())
                built = self._build_managed_automation(
                    profile_auto=profile_auto,
                    subject=subject,
                    subject_id=subject_id,
                    guid=guid,
                    source=None,
                )
                result.created += 1
            else:
                guid = self._get_guid(existing) or str(uuid.uuid4())
                replacement_guids.add(guid)
                built = self._build_managed_automation(
                    profile_auto=profile_auto,
                    subject=subject,
                    subject_id=subject_id,
                    guid=guid,
                    source=existing,
                )
                if migrated:
                    result.migrated += 1
                if self._automation_changed(existing, built):
                    result.updated += 1
                reused_guids.add(guid)

            # 更新绑定关系
            binding.id = guid
            desired_entries.append((guid, built, binding))

        # 清理和保存配置
        remove_guids = managed_guids | replacement_guids
        retained = [item for item in automations if self._get_guid(item) not in remove_guids]
        retained.extend(item for _, item, _ in desired_entries)

        deleted_guids = remove_guids - reused_guids
        result.deleted = len(deleted_guids)

        ci_manager.ci_automations = retained
        if not ci_manager._save_automations():
            result.errors.append("保存 ClassIsland 自动化配置失败")
            return result

        # 重新加载配置
        with self._suppress_reload_error(result):
            ci_manager.reload_config()

        return result

    @staticmethod
    def _automation_changed(old: dict, new: dict) -> bool:
        return old != new

    @staticmethod
    def _get_guid(automation: dict) -> str | None:
        try:
            return automation["ActionSet"]["Guid"]
        except Exception:
            return None

    @staticmethod
    def _get_name(automation: dict) -> str:
        try:
            return automation["ActionSet"]["Name"]
        except Exception:
            return ""

    @staticmethod
    def _get_args(automation: dict) -> str:
        try:
            return automation["ActionSet"]["Actions"][0]["Settings"]["Args"]
        except Exception:
            return ""

    @staticmethod
    def _get_subject_id(automation: dict) -> str | None:
        try:
            return automation["Ruleset"]["Groups"][0]["Rules"][0]["Settings"]["SubjectId"]
        except Exception:
            return None

    @staticmethod
    def _get_pretime(automation: dict) -> int:
        try:
            return int(automation["Triggers"][0]["Settings"]["TimeSeconds"])
        except Exception:
            return config.ClassIsland.DefaultPreTime

    @staticmethod
    def _get_enabled(automation: dict, fallback: bool = True) -> bool:
        try:
            return bool(automation["ActionSet"]["IsEnabled"])
        except Exception:
            return fallback

    def _is_managed_automation(self, automation: dict, tracked_guids: set[str | None]) -> bool:
        """判断自动化配置是否受管理"""
        guid = self._get_guid(automation)
        if guid in tracked_guids:
            return True
        if not self._get_name(automation).startswith(EA_PREFIX):
            return False
        profile_id = _extract_arg(self._get_args(automation), "-i", "--id")
        return profile_id is not None

    def _find_managed_by_subject(
        self,
        guid_to_automation: dict[str, dict],
        managed_guids: set[str],
        subject_id: str,
        exclude: set[str],
    ) -> dict | None:
        """根据科目 ID 查找受管理的自动化配置"""
        for guid in managed_guids:
            if guid in exclude:
                continue
            automation = guid_to_automation.get(guid)
            if not automation:
                continue
            if self._get_subject_id(automation) == subject_id:
                return automation
        return None

    def _find_legacy_candidate(
        self,
        automations: list[dict],
        subject_id: str,
        account: str,
        password: str,
        exclude: set[str],
    ) -> dict | None:
        """查找遗留的自动化配置用于迁移"""
        for automation in automations:
            guid = self._get_guid(automation)
            if guid in exclude:
                continue
            if not self._get_name(automation).startswith(EA_PREFIX):
                continue
            if self._get_subject_id(automation) != subject_id:
                continue

            args = self._get_args(automation)
            if _extract_arg(args, "-i", "--id"):
                continue

            automation_account = _extract_arg(args, "-a", "--account")
            automation_password = _extract_arg(args, "-p", "--password")
            if automation_account == account and automation_password == password:
                return automation

        return None

    def _build_desired_bindings(
        self,
        profile_data: Profile,
        bindings: list[BindingItem],
        subject_map: dict[str, CiSubject],
        result: SyncResult,
    ) -> dict[str, tuple[BindingItem, EasiAutomation, CiSubject]]:
        """构建期望的绑定关系"""
        desired: dict[str, tuple[BindingItem, EasiAutomation, CiSubject]] = {}

        for binding in bindings:
            subject_id = self._resolve_subject_id(binding, subject_map)
            if not subject_id:
                result.errors.append(
                    f"科目无效: {binding.subject.name} (provider={binding.subject.provider}, id={binding.subject.id})"
                )
                continue

            profile_auto = profile_data.get_automation(binding.automation_id)
            if profile_auto is None:
                result.errors.append(f"档案不存在: {binding.automation_id}")
                continue
            if not profile_auto.enabled:
                result.errors.append(f"档案已禁用: {profile_auto.account or binding.automation_id}")
                continue
            if profile_auto.account.strip() == "" or profile_auto.password.strip() == "":
                result.errors.append(f"档案缺少账号或密码: {profile_auto.account or binding.automation_id}")
                continue

            desired[subject_id] = (binding, profile_auto, subject_map[subject_id])

        return desired

    @staticmethod
    def _resolve_subject_id(binding: BindingItem, subject_map: dict[str, CiSubject]) -> str | None:
        """解析科目 ID"""
        subject = binding.subject

        if subject.id and subject.id in subject_map:
            return subject.id

        for subject_id, candidate in subject_map.items():
            if candidate.name.strip().lower() == subject.name.strip().lower():
                subject.id = subject_id
                subject.name = candidate.name
                return subject_id

        return None

    def _build_managed_automation(
        self,
        profile_auto: EasiAutomation,
        subject: CiSubject,
        subject_id: str,
        guid: str,
        source: dict | None,
    ) -> dict[str, Any]:
        """构建受管理的自动化配置"""
        pretime = self._get_pretime(source) if source else config.ClassIsland.DefaultPreTime
        enabled = self._get_enabled(source, fallback=True) if source else True

        return {
            "Ruleset": {
                "Mode": 0,
                "IsReversed": False,
                "Groups": [
                    {
                        "Rules": [
                            {
                                "IsReversed": False,
                                "Id": "classisland.lessons.nextSubject",
                                "Settings": {"SubjectId": subject_id},
                            },
                            {
                                "IsReversed": True,
                                "Id": "classisland.lessons.previousSubject",
                                "Settings": {"SubjectId": subject_id},
                            },
                        ],
                        "Mode": 1,
                        "IsReversed": False,
                        "IsEnabled": True,
                    }
                ],
            },
            "ActionSet": {
                "IsEnabled": enabled,
                "Name": profile_auto.get_automation_name(subject.name),
                "Guid": guid,
                "IsOn": False,
                "Actions": [
                    {
                        "Id": "classisland.os.run",
                        "Settings": {
                            "Value": str(EA_EXECUTABLE),
                            "Args": f"login --id {profile_auto.id}",
                        },
                    }
                ],
                "IsRevertEnabled": False,
            },
            "Triggers": [
                {
                    "Id": "classisland.lessons.preTimePoint",
                    "Settings": {"TargetState": 1, "TimeSeconds": pretime},
                }
            ],
            "IsConditionEnabled": True,
        }

    class _suppress_reload_error:  # noqa: N801
        def __init__(self, result: SyncResult | None = None):
            self.result = result

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, _tb):
            if exc_type is None:
                return False
            message = f"刷新 ClassIsland 配置失败: {exc}"
            logger.error(message)
            if self.result is not None:
                self.result.errors.append(message)
            return True
