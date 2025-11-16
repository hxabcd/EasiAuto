import json
import os
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import psutil
import win32api
from pydantic import BaseModel, Field, field_validator

from utils import get_executable_path

# ClassIsland 联动相关配置


class CiSubject(BaseModel):
    id: str
    name: str
    initial: Optional[str] = None
    teacher_name: Optional[str] = None
    is_out_door: Optional[bool] = None


class EasiAutomation(BaseModel):
    account: str
    password: str
    subject_id: str
    pretime: int = 300
    guid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str = "自动登录希沃白板"
    teacher_name: Optional[str] = None
    enabled: bool = True

    @field_validator("pretime")
    def validate_pretime(cls, v):
        if v < 0:
            raise ValueError("提前时间不能为负数")
        return v

    @property
    def full_display_name(self) -> str:
        if self.teacher_name:
            return f"[EasiAuto] {self.display_name} - {self.teacher_name}"
        return f"[EasiAuto] {self.display_name}"

    @property
    def item_display_name(self) -> str:
        if self.teacher_name:
            return f"{self.display_name} - {self.teacher_name}"
        return self.display_name


class CiAutomationManager:
    """ClassIsland自动化管理器"""

    def __init__(self, path: Path | str):
        self.subjects: Dict[str, CiSubject] = {}
        self.automations: Dict[str, EasiAutomation] = {}
        self.ci_settings: dict = {}
        self.ci_profile: dict = {}
        self.ci_automations: List[dict] = []

        self.init_ci(path)

    @property
    def is_ci_running(self) -> bool:
        for p in psutil.process_iter(["pid", "exe"]):
            try:
                if p.info["exe"] and Path(p.info["exe"]).resolve() == self.ci_executable_path:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return False

    def open_ci(self):
        os.startfile(self.ci_executable_path)

    def close_ci(self):
        os.system(f"taskkill /f /im {self.ci_executable_path.name}")

    def init_ci(self, exe_path: Path | str):
        """获取CI版本，定位数据目录并初始化"""
        exe_path = Path(exe_path)
        self.ci_executable_path = exe_path

        info = win32api.GetFileVersionInfo(str(exe_path), "\\")
        ms, ls = info["FileVersionMS"], info["FileVersionLS"]
        version = (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)

        root = exe_path.parent
        if version > (1, 7, 100, 0):  # v2
            # ClassIsland / app-[version]-0 / ClassIsland.Desktop.exe
            # ClassIsland / data
            self.ci_data_path = root.parent / "data"
            self.is_v2 = True
        else:  # v1
            self.ci_data_path = root
            self.is_v2 = False

        self._validate_ci_structure()
        self.reload_config()

    def _validate_ci_structure(self):
        """验证ClassIsland目录结构"""
        if not self.ci_data_path.exists():
            raise FileNotFoundError(f"CI 程序目录 {self.ci_data_path} 不存在")

        required_paths = [
            self.ci_data_path / "Settings.json",
            self.ci_data_path / "Profiles",
            self.ci_data_path / "Config" / "Automations",
        ]

        for path in required_paths:
            if not path.exists():
                raise FileNotFoundError(f"CI 目录结构不完整: {path} 不存在")

    def reload_config(self):
        """重新加载所有配置"""
        self._load_settings()
        self._load_profile()
        self._load_automations()
        self._build_indexes()

    def _load_settings(self):
        """加载CI设置"""
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
            if name.startswith("[EasiAuto]"):
                easi_auto = self._parse_easi_automation(automation)
                if easi_auto:
                    self.automations[easi_auto.guid] = easi_auto

    def _parse_easi_automation(self, automation: dict) -> Optional[EasiAutomation]:
        """解析EasiAuto自动化配置"""
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

            assert account
            assert password

            return EasiAutomation(
                guid=guid,
                account=account,
                password=password,
                subject_id=subject_id,
                pretime=pretime,
                display_name=display_name,
                teacher_name=teacher_name,
                enabled=enabled,
            )
        except (KeyError, IndexError, AttributeError) as e:
            print(f"解析自动化配置时出错: {e}")
            return None

    def get_subject_by_id(self, subject_id: str) -> Optional[CiSubject]:
        """根据ID获取科目"""
        return self.subjects.get(subject_id)

    def get_automation_by_guid(self, guid: str) -> Optional[EasiAutomation]:
        """根据GUID获取自动化"""
        return self.automations.get(guid)

    def get_automations_by_subject(self, subject_id: str) -> List[EasiAutomation]:
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
            return True
        return False

    def update_automation(self, _guid: str, **updates) -> bool:
        """更新自动化配置

        Args:
            guid: 自动化GUID
            **updates: 要更新的字段，如 account, password, subject_id, pretime, display_name, teacher_name

        Returns:
            bool: 更新是否成功
        """
        if _guid not in self.automations:
            raise ValueError(f"自动化GUID {_guid} 不存在")

        original_automation = self.automations[_guid]

        # 构建更新后的自动化对象
        update_data = original_automation.model_dump()
        update_data.update(updates)

        # 验证科目是否存在（如果更新了subject_id）
        if "subject_id" in updates and updates["subject_id"] not in self.subjects:
            raise ValueError(f"科目ID {updates['subject_id']} 不存在")

        updated_automation = EasiAutomation(**update_data)

        # 从CI自动化列表中移除旧的
        self.ci_automations = [auto for auto in self.ci_automations if auto["ActionSet"]["Guid"] != _guid]

        # 添加更新后的
        ci_automation = self._build_ci_automation(updated_automation)
        self.ci_automations.append(ci_automation)

        # 保存到文件
        if self._save_automations():
            self.automations[_guid] = updated_automation
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
                                "Settings": {"SubjectId": automation.subject_id, "IsActive": False},
                                "IsActive": False,
                            },
                            {
                                "IsReversed": True,
                                "Id": "classisland.lessons.previousSubject",
                                "Settings": {"SubjectId": automation.subject_id, "IsActive": False},
                                "IsActive": False,
                            },
                        ],
                        "Mode": 1,
                        "IsReversed": False,
                        "IsEnabled": True,
                        "IsActive": False,
                    }
                ],
                "IsActive": False,
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
                            "Value": str(get_executable_path() / "EasiAuto.exe"),
                            "Args": f"login -a {automation.account} -p {automation.password}",
                            "IsActive": False,
                        },
                        "IsActive": False,
                    }
                ],
                "IsRevertEnabled": False,
                "IsActive": False,
            },
            "Triggers": [
                {
                    "Id": "classisland.lessons.preTimePoint",
                    "Settings": {"TargetState": 1, "TimeSeconds": automation.pretime},
                    "IsActive": False,
                }
            ],
            "IsConditionEnabled": True,
            "IsActive": False,
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
            print(f"保存自动化配置时出错: {e}")
            return False

    def list_subjects(self) -> List[CiSubject]:
        """获取所有科目列表"""
        return list(self.subjects.values())

    def list_automations(self) -> List[EasiAutomation]:
        """获取所有自动化列表"""
        return list(self.automations.values())


### 下面是一些用于CLI交互的函数 ###
### 或许说，测试残留？ ###


def input_with_default(prompt: str, default: str = "") -> str:
    """带默认值的输入函数"""
    if default:
        user_input = input(f"{prompt} [{default}]: ")
        return user_input if user_input.strip() else default
    else:
        return input(f"{prompt}: ")


def edit_automation_interactive(manager: CiAutomationManager, automation: EasiAutomation) -> bool:
    """交互式编辑自动化配置"""
    print(f"\n正在编辑自动化: {automation.full_display_name}")
    print("=" * 50)

    # 显示当前信息
    current_subject = manager.get_subject_by_id(automation.subject_id)
    print(f"当前科目: {current_subject.name if current_subject else '未知科目'}")
    print(f"当前账号: {automation.account}")
    print(f"当前提前时间: {automation.pretime}秒")
    print(f"当前显示名称: {automation.display_name}")
    print(f"当前教师名称: {automation.teacher_name or '未设置'}")

    updates = {}

    # 选择是否修改科目
    change_subject = input("\n是否修改科目? (y/N): ").lower() == "y"
    if change_subject:
        print("\n选择新科目:")
        subjects = manager.list_subjects()
        for i, subject in enumerate(subjects):
            print(f"  [{i}] {subject.name} ({subject.teacher_name or '无教师'})")

        try:
            subject_index = int(input("输入科目序号: "))
            selected_subject = subjects[subject_index]
            updates["subject_id"] = selected_subject.id
            print(f"已选择科目: {selected_subject.name}")
        except (ValueError, IndexError):
            print("无效的科目序号，保持原科目")

    # 修改账号
    change_account = input("\n是否修改账号? (y/N): ").lower() == "y"
    if change_account:
        new_account = input_with_default("新账号", automation.account)
        updates["account"] = new_account

    # 修改密码
    change_password = input("\n是否修改密码? (y/N): ").lower() == "y"
    if change_password:
        new_password = input_with_default("新密码", automation.password)
        updates["password"] = new_password

    # 修改提前时间
    change_pretime = input("\n是否修改提前时间? (y/N): ").lower() == "y"
    if change_pretime:
        try:
            new_pretime = input_with_default("新提前时间(秒)", str(automation.pretime))
            updates["pretime"] = int(new_pretime)
        except ValueError:
            print("无效的时间格式，保持原时间")

    # 修改显示名称
    change_display_name = input("\n是否修改显示名称? (y/N): ").lower() == "y"
    if change_display_name:
        new_display_name = input_with_default("新显示名称", automation.display_name)
        updates["display_name"] = new_display_name

    # 修改教师名称
    change_teacher_name = input("\n是否修改教师名称? (y/N): ").lower() == "y"
    if change_teacher_name:
        new_teacher_name = input_with_default("新教师名称(留空清除)", automation.teacher_name or "")
        updates["teacher_name"] = new_teacher_name if new_teacher_name.strip() else None

    # 如果没有修改，直接返回
    if not updates:
        print("没有进行任何修改")
        return False

    # 显示修改摘要
    print("\n修改摘要:")
    print("-" * 30)
    for key, value in updates.items():
        old_value = getattr(automation, key)
        print(f"  {key}: {old_value} -> {value}")

    # 确认修改
    confirm = input("\n确认以上修改? (y/N): ").lower() == "y"
    if confirm:
        return manager.update_automation(automation.guid, **updates)
    else:
        print("修改已取消")
        return False


# 使用示例
def main():
    from utils import get_ci_executable_path

    path = get_ci_executable_path()

    try:
        manager = CiAutomationManager(path)  # type: ignore
        print("ClassIsland 自动化管理器初始化成功")
    except FileNotFoundError as e:
        print(f"初始化失败: {e}")
        return
    except Exception as e:
        print(f"初始化过程中发生错误: {e}")
        return

    while True:
        print("\n" + "=" * 50)
        print("ClassIsland 自动化管理器")
        print("=" * 50)
        print("0. 终止 CI")
        print("1. 显示所有科目和自动化")
        print("2. 新建自动化")
        print("3. 修改自动化")
        print("4. 删除自动化")
        print("5. 重新加载配置")
        print("--------")

        try:
            action = int(input("输入操作序号："))
        except ValueError:
            print("请输入有效的数字")
            continue

        match action:
            case 0:
                print("正在终止 ClassIsland...")
                os.system("taskkill /f /im ClassIsland.exe")
                print("程序退出")
                break

            case 1:
                print("\n所有科目:")
                subjects = manager.list_subjects()
                for i, subject in enumerate(subjects):
                    automations = manager.get_automations_by_subject(subject.id)
                    auto_count = len(automations)
                    status = f"({auto_count}个自动化)" if auto_count > 0 else "(无自动化)"
                    print(f"  [{i}] {subject.name} - {subject.teacher_name or '无教师'} {status}")

                print("\n所有自动化:")
                automations = manager.list_automations()
                if not automations:
                    print("  暂无自动化配置")
                else:
                    for i, automation in enumerate(automations):
                        subject = manager.get_subject_by_id(automation.subject_id)
                        subject_name = subject.name if subject else "未知科目"
                        print(f"  [{i}] {automation.full_display_name}")
                        print(f"      科目: {subject_name}")
                        print(f"      账号: {automation.account}")
                        print(f"      密码: {'*' * len(automation.password)}")
                        print(f"      提前时间: {automation.pretime}秒")
                        print(f"      GUID: {automation.guid}")

            case 2:
                print("\n选择科目:")
                subjects = manager.list_subjects()
                for i, subject in enumerate(subjects):
                    # 检查是否已有自动化
                    existing = manager.get_automations_by_subject(subject.id)
                    has_auto = "✓" if existing else " "
                    print(f"  [{i}] {has_auto} {subject.name} ({subject.teacher_name or '无教师'})")

                try:
                    subject_index = int(input("输入科目序号: "))
                    selected_subject = subjects[subject_index]
                except (ValueError, IndexError):
                    print("无效的科目序号")
                    continue

                account = input("账号: ")
                if not account:
                    print("账号不能为空")
                    continue

                password = input("密码: ")
                if not password:
                    print("密码不能为空")
                    continue

                pretime = input("提前时间(秒，默认300): ")
                display_name = input("显示名称(默认'自动登录希沃白板'): ")
                teacher_name = input("教师名称(可选): ")

                automation = EasiAutomation(
                    subject_id=selected_subject.id,
                    account=account,
                    password=password,
                    pretime=int(pretime) if pretime else 300,
                    display_name=display_name or "自动登录希沃白板",
                    teacher_name=teacher_name or None,
                )

                if manager.create_automation(automation):
                    print("自动化创建成功")
                else:
                    print("自动化创建失败")

            case 3:
                print("\n选择要修改的自动化:")
                automations = manager.list_automations()
                if not automations:
                    print("暂无自动化配置可修改")
                    continue

                for i, auto in enumerate(automations):
                    subject = manager.get_subject_by_id(auto.subject_id)
                    subject_name = subject.name if subject else "未知科目"
                    print(f"  [{i}] {auto.full_display_name} (科目: {subject_name})")

                try:
                    auto_index = int(input("输入自动化序号: "))
                    selected_auto = automations[auto_index]
                except (ValueError, IndexError):
                    print("无效的自动化序号")
                    continue

                if edit_automation_interactive(manager, selected_auto):
                    print("自动化修改成功")
                else:
                    print("自动化修改失败或已取消")

            case 4:
                print("\n选择要删除的自动化:")
                automations = manager.list_automations()
                if not automations:
                    print("暂无自动化配置可删除")
                    continue

                for i, auto in enumerate(automations):
                    subject = manager.get_subject_by_id(auto.subject_id)
                    subject_name = subject.name if subject else "未知科目"
                    print(f"  [{i}] {auto.full_display_name} (科目: {subject_name})")

                try:
                    auto_index = int(input("输入自动化序号: "))
                    selected_auto = automations[auto_index]
                except (ValueError, IndexError):
                    print("无效的自动化序号")
                    continue

                confirm = input(f"确认删除自动化 '{selected_auto.full_display_name}'? (y/N): ")
                if confirm.lower() == "y":
                    if manager.delete_automation(selected_auto.guid):
                        print("自动化删除成功")
                    else:
                        print("自动化删除失败")
                else:
                    print("删除操作已取消")

            case 5:
                manager.reload_config()
                print("配置重新加载完成")

            case _:
                print("无效的操作")


if __name__ == "__main__":
    main()
