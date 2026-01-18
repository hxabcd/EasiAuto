import json
import os
import re
import uuid
from pathlib import Path

import pywintypes
import win32api
import win32con
import win32event
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from PySide6.QtCore import QObject, Signal

from config import config
from consts import EA_EXECUTABLE, EA_PREFIX


class CiSubject(BaseModel):
    id: str
    name: str
    initial: str | None = None
    teacher_name: str | None = None
    is_out_door: bool | None = None


class EasiAutomation(BaseModel):
    account: str
    password: str
    subject_id: str
    pretime: int = config.ClassIsland.DefaultPreTime
    guid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str = config.ClassIsland.DefaultDisplayName
    teacher_name: str | None = None
    enabled: bool = True

    @field_validator("pretime")
    def validate_pretime(cls, v):
        if v < 0:
            raise ValueError("提前时间不能为负数")
        return v

    @property
    def full_display_name(self) -> str:
        if self.teacher_name:
            return f"{EA_PREFIX} {self.display_name} - {self.teacher_name}"
        return f"{EA_PREFIX} {self.display_name}"

    @property
    def item_display_name(self) -> str:
        if self.teacher_name:
            return f"{self.display_name} - {self.teacher_name}"
        return self.display_name

    @property
    def shortcut_name(self) -> str:
        if self.teacher_name:
            label = self.teacher_name
        elif manager and (subject := manager.get_subject_by_id(self.subject_id)):
            label = subject.name
        else:
            label = self.account

        return f"希沃自动登录（{label}）"


class CiManager(QObject):
    """ClassIsland 自动化管理器"""

    # 数据变更信号，参数为 GUID
    automationCreated = Signal(str)
    automationUpdated = Signal(str)
    automationDeleted = Signal(str)

    def __init__(self, path: Path | str):
        super().__init__()
        self.subjects: dict[str, CiSubject] = {}
        self.automations: dict[str, EasiAutomation] = {}
        self.ci_settings: dict = {}
        self.ci_profile: dict = {}
        self.ci_automations: list[dict] = []

        self.init_ci(path)

    @property
    def is_ci_running(self) -> bool:
        """检查 ClassIsland 是否正在运行"""
        # 优先使用 Mutex 检查
        try:
            handle = win32event.OpenMutex(win32con.SYNCHRONIZE, False, "Global\\ClassIsland.Lock")
            if handle:
                win32api.CloseHandle(handle)
                return True
        except pywintypes.error as e:
            # ERROR_ACCESS_DENIED (5) 也表示 Mutex 存在但权限不足
            if e.winerror == 5:
                return True
        # except Exception:
        #     # 回退到全量进程遍历
        #     for p in psutil.process_iter(["name"]):
        #         try:
        #             if p.info["name"] in ["ClassIsland.exe", "ClassIsland.Desktop.exe"]:
        #                 return True
        #         except (psutil.NoSuchProcess, psutil.AccessDenied):
        #             pass
        return False

    def open_ci(self):
        os.startfile(self.ci_executable_path, cwd=self.ci_executable_path.parent)

    def close_ci(self):
        os.system(f"taskkill /f /im {'ClassIsland.Desktop.exe' if self.is_v2 else 'ClassIsland.exe'}")

    def init_ci(self, exe_path: Path | str):
        """获取CI版本，定位数据目录并初始化"""
        exe_path = Path(exe_path)

        info = win32api.GetFileVersionInfo(str(exe_path), "\\")
        ms, ls = info["FileVersionMS"], info["FileVersionLS"]
        version = (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)

        root = exe_path.parent
        if version > (1, 7, 100, 0):  # v2
            self.ci_data_path = root / "data"
            self.is_v2 = True
        else:  # v1
            self.ci_data_path = root
            self.is_v2 = False

        self.ci_executable_path = exe_path

        self._validate_ci_structure()
        self.reload_config()

    def _validate_ci_structure(self):
        """验证 ClassIsland 目录结构"""
        if not self.ci_data_path.exists():
            raise FileNotFoundError(f"ClassIsland 数据目录 {self.ci_data_path} 不存在")

        required_paths = [
            self.ci_data_path / "Settings.json",
            self.ci_data_path / "Profiles",
            self.ci_data_path / "Config" / "Automations",
        ]

        for path in required_paths:
            if not path.exists():
                raise FileNotFoundError(f"ClassIsland 数据目录结构不完整: {path} 不存在")

    def reload_config(self):
        """重新加载所有配置"""
        self._load_settings()
        self._load_profile()
        self._load_automations()
        self._build_indexes()

    def _load_settings(self):
        """加载 ClassIsland 设置"""
        ci_setting_path = self.ci_data_path / "Settings.json"
        with ci_setting_path.open(encoding="utf-8") as f:
            self.ci_settings = json.load(f)

    def _load_profile(self):
        """加载当前档案"""
        ci_profile_name = self.ci_settings["SelectedProfile"]
        ci_profile_path = self.ci_data_path / "Profiles" / ci_profile_name

        if not ci_profile_path.exists():
            raise FileNotFoundError(f"档案 {ci_profile_name} 不存在")

        with ci_profile_path.open(encoding="utf-8") as f:
            self.ci_profile = json.load(f)

    def _load_automations(self):
        """加载自动化配置"""
        ci_automation_name = self.ci_settings["CurrentAutomationConfig"]
        ci_automations_path = self.ci_data_path / "Config" / "Automations" / f"{ci_automation_name}.json"

        if not ci_automations_path.exists():
            raise FileNotFoundError(f"自动化配置 {ci_automation_name} 不存在")

        with ci_automations_path.open(encoding="utf-8") as f:
            self.ci_automations = json.load(f)

    def _build_indexes(self):
        """构建科目和自动化的索引"""
        # 构建科目索引
        self.subjects.clear()
        ci_subjects: dict = self.ci_profile["Subjects"]
        for subject_id, subject_data in ci_subjects.items():
            self.subjects[subject_id] = CiSubject(
                id=subject_id,
                name=subject_data.get("Name", "N/A"),
                initial=subject_data.get("Initial"),
                teacher_name=subject_data.get("TeacherName"),
                is_out_door=subject_data.get("IsOutDoor"),
            )

        # 构建自动化索引
        self.automations.clear()
        for automation in self.ci_automations:
            name: str = automation["ActionSet"]["Name"]
            if name.startswith(EA_PREFIX):
                easi_auto = self._parse_automation(automation)
                if easi_auto:
                    self.automations[easi_auto.guid] = easi_auto

    def _parse_automation(self, automation: dict) -> EasiAutomation | None:
        """解析 EasiAuto 生成的自动化配置"""
        try:
            name: str = automation["ActionSet"]["Name"]
            args: str = automation["ActionSet"]["Actions"][0]["Settings"]["Args"]
            subject_id: str = automation["Ruleset"]["Groups"][0]["Rules"][0]["Settings"]["SubjectId"]
            pretime: int = automation["Triggers"][0]["Settings"]["TimeSeconds"]
            guid: str = automation["ActionSet"]["Guid"]
            enabled: bool = automation["ActionSet"]["IsEnabled"]

            # 匹配账号密码
            account_match = re.search(r"(?:-a|--account)\s+(\S+)", args)
            account = account_match.group(1) if account_match else None
            password_match = re.search(r"(?:-p|--password)\s+(\S+)", args)
            password = password_match.group(1) if password_match else None

            if not all([account, password, subject_id]):
                return None

            # 解析显示名称和教师名称
            display_name = "自动登录希沃白板"
            teacher_name = None

            pattern = r"^\[EasiAuto\]\s*(.+?)(?:\s*-\s*(.+))?$"
            match = re.match(pattern, name)
            if match:
                display_name_part, teacher_name_part = match.groups()
                if display_name_part:
                    display_name = display_name_part
                teacher_name = teacher_name_part

            if not account or not password:
                logger.warning(f"解析自动化 {guid or '未知自动化'} 时缺失关键数据")
                return None

            return EasiAutomation(
                account=account,
                password=password,
                subject_id=subject_id,
                pretime=pretime,
                guid=guid,
                display_name=display_name,
                teacher_name=teacher_name,
                enabled=enabled,
            )
        except (KeyError, IndexError, AttributeError) as e:
            logger.warning(f"解析自动化配置时出错: {e}")
            return None

    def get_subject_by_id(self, subject_id: str) -> CiSubject | None:
        """根据ID获取科目"""
        return self.subjects.get(subject_id)

    def get_automation_by_guid(self, guid: str) -> EasiAutomation | None:
        """根据GUID获取自动化"""
        return self.automations.get(guid)

    def get_automations_by_subject(self, subject_id: str) -> list[EasiAutomation]:
        """获取指定科目的所有自动化"""
        return [auto for auto in self.automations.values() if auto.subject_id == subject_id]

    def create_automation(self, automation: EasiAutomation) -> bool:
        """创建新的自动化"""
        # 验证科目存在
        if automation.subject_id not in self.subjects:
            raise ValueError(f"科目ID {automation.subject_id} 不存在")

        # 验证GUID唯一性
        if automation.guid in self.automations:
            raise ValueError(f"自动化GUID {automation.guid} 已存在")

        # 创建CI自动化配置
        ci_automation = self._build_ci_automation(automation)
        self.ci_automations.append(ci_automation)

        # 保存到文件
        if self._save_automations():
            self.automations[automation.guid] = automation
            self.automationCreated.emit(automation.guid)
            return True
        return False

    def update_automation(self, _guid: str, **updates) -> bool:
        """更新自动化配置

        Args:
            guid: 自动化GUID
            **updates: 待更新的字段

        Returns:
            bool: 更新是否成功
        """
        if _guid not in self.automations:
            raise ValueError(f"自动化GUID {_guid} 不存在")

        original_automation = self.automations[_guid]

        # 构建更新后的自动化对象
        update_data = original_automation.model_dump()
        update_data.update(updates)

        # 验证科目
        if "subject_id" in updates and updates["subject_id"] not in self.subjects:
            raise ValueError(f"科目ID {updates['subject_id']} 不存在")

        updated_automation = EasiAutomation(**update_data)

        # 替换更新后的自动化并保存
        self.ci_automations = [auto for auto in self.ci_automations if auto["ActionSet"]["Guid"] != _guid]

        new_ci_automation = self._build_ci_automation(updated_automation)
        self.ci_automations.append(new_ci_automation)

        if self._save_automations():
            self.automations[_guid] = updated_automation
            self.automationUpdated.emit(_guid)
            return True
        return False

    def delete_automation(self, guid: str) -> bool:
        """删除自动化"""
        if guid not in self.automations:
            raise ValueError(f"自动化GUID {guid} 不存在")

        # 从CI自动化列表中移除
        self.ci_automations = [auto for auto in self.ci_automations if auto["ActionSet"]["Guid"] != guid]

        # 保存到文件
        if self._save_automations():
            del self.automations[guid]
            self.automationDeleted.emit(guid)
            return True
        return False

    def _build_ci_automation(self, automation: EasiAutomation) -> dict:
        """构建CI自动化配置对象"""
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
                                "Settings": {"SubjectId": automation.subject_id},
                            },
                            {
                                "IsReversed": True,
                                "Id": "classisland.lessons.previousSubject",
                                "Settings": {"SubjectId": automation.subject_id},
                            },
                        ],
                        "Mode": 1,
                        "IsReversed": False,
                        "IsEnabled": True,
                    }
                ],
            },
            "ActionSet": {
                "IsEnabled": automation.enabled,
                "Name": automation.full_display_name,
                "Guid": automation.guid,
                "IsOn": False,
                "Actions": [
                    {
                        "Id": "classisland.os.run",
                        "Settings": {
                            "Value": str(EA_EXECUTABLE),
                            "Args": f"login -a {automation.account} -p {automation.password}",
                        },
                    }
                ],
                "IsRevertEnabled": False,
            },
            "Triggers": [
                {
                    "Id": "classisland.lessons.preTimePoint",
                    "Settings": {"TargetState": 1, "TimeSeconds": automation.pretime},
                }
            ],
            "IsConditionEnabled": True,
        }

    def _save_automations(self) -> bool:
        """保存自动化配置到文件"""
        try:
            ci_automation_name = self.ci_settings["CurrentAutomationConfig"]
            ci_automations_path = self.ci_data_path / "Config" / "Automations" / f"{ci_automation_name}.json"

            with ci_automations_path.open("w", encoding="utf-8") as f:
                json.dump(self.ci_automations, f)
            return True
        except Exception as e:
            logger.error(f"保存自动化配置时出错: {e}")
            return False

    def list_subjects(self) -> list[CiSubject]:
        """获取所有科目列表"""
        return list(self.subjects.values())

    def list_automations(self) -> list[EasiAutomation]:
        """获取所有自动化列表"""
        return list(self.automations.values())


class _CiManagerProxy:
    def __init__(self):
        self._impl: CiManager | None = None

    def initialize(self, path: Path):
        self._impl = CiManager(path)

    def __getattr__(self, item):
        if self._impl:
            return getattr(self._impl, item)
        raise AttributeError(f"Manager not initialized, cannot access {item}")

    def __bool__(self):
        return self._impl is not None


manager: CiManager | None = _CiManagerProxy()  # type: ignore
