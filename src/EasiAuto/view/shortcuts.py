"""Windows 快捷方式的创建与维护。"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

import win32com.client
from loguru import logger

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

from EasiAuto.consts import EA_BASEDIR, EA_EXECUTABLE, EA_RESDIR


def get_start_menu_programs() -> Path | None:
    """获取开始菜单"程序"文件夹路径，获取失败时返回 None"""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        return Path(shell.SpecialFolders("Programs"))
    except Exception as e:
        logger.error(f"获取开始菜单目录失败: {e}")
        return None


def create_shortcut(
    args: str,
    name: str,
    icon_name: str = "EasiAuto",
    show_result_to: QWidget | None = None,
    folder: str | Path | None = None,
) -> Path | None:
    """创建 EasiAuto 快捷方式

    Args:
        args: 启动参数
        name: 快捷方式名称（不含 .lnk 扩展名）
        icon_name: 图标名称（图标目录下的文件名，不含 .ico 扩展名）
        show_result_to: 创建完成后提示的目标控件，None 则不提示
        folder: 快捷方式存放目录；None 表示桌面

    Returns:
        创建的快捷方式路径；失败返回 None
    """
    try:
        name = name + ".lnk"

        shell = win32com.client.Dispatch("WScript.Shell")
        target_dir = Path(folder) if folder else Path(shell.SpecialFolders("Desktop"))
        target_dir.mkdir(parents=True, exist_ok=True)
        shortcut_path = target_dir / name

        # 如果快捷方式已存在，先删除（解决覆盖保存时的权限问题）
        if shortcut_path.exists():
            shortcut_path.unlink(missing_ok=True)
            logger.debug(f"已删除现有快捷方式: {shortcut_path}")

        logger.info(f"创建快捷方式: {shortcut_path}")

        icon_path = EA_RESDIR / "icons" / f"{icon_name}.ico"
        if not icon_path.exists():
            logger.warning(f"图标文件不存在: {icon_path}, 使用默认图标")
            icon_path = EA_RESDIR / "icons" / "EasiAuto.ico"

        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = str(EA_EXECUTABLE)
        shortcut.Arguments = args
        shortcut.WorkingDirectory = str(EA_BASEDIR)
        shortcut.IconLocation = str(icon_path)
        shortcut.Save()

        logger.success(f"创建成功: {shortcut_path}")
        location = "开始菜单" if folder else "桌面"
        if show_result_to:
            InfoBar.success(
                title="成功",
                content=f"已在{location}创建 {name}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=show_result_to,
            )
        return shortcut_path
    except Exception as e:
        logger.error(f"创建快捷方式失败: {e}")
        if show_result_to:
            InfoBar.error(
                title="创建失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=show_result_to,
            )
        return None


def migrate_desktop_shortcut_icon() -> int:
    """迁移桌面 EasiAuto 快捷方式图标路径到新位置。"""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        desktop_path = Path(shell.SpecialFolders("Desktop"))
    except Exception as e:
        logger.warning(f"获取桌面路径失败，跳过快捷方式图标迁移: {e}")
        return 0

    old_icon_path = EA_RESDIR / "EasiAutoShortcut.ico"
    new_icon_path = EA_RESDIR / "icons" / "EasiAutoShortcut.ico"
    assert new_icon_path.exists()

    migrated_count = 0

    # 扫描桌面所有快捷方式，仅处理目标程序为 EasiAuto 的项。
    for lnk_path in desktop_path.glob("*.lnk"):
        with suppress(Exception):
            shortcut = shell.CreateShortcut(str(lnk_path))

            target_path = (shortcut.TargetPath or "").strip()
            if Path(target_path) != EA_EXECUTABLE:
                continue

            icon_location = (shortcut.IconLocation or "").strip()
            if not icon_location:
                continue
            current_icon_path = icon_location.split(",", 1)[0].strip().strip('"')

            if Path(current_icon_path) == old_icon_path:
                shortcut.IconLocation = f"{new_icon_path},0"
                shortcut.Save()
                migrated_count += 1
            elif Path(current_icon_path) == new_icon_path:
                continue

    if migrated_count > 0:
        logger.success(f"已迁移 {migrated_count} 个桌面快捷方式图标")
    return migrated_count
