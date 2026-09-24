"""进程终止与外部程序探测。"""

from __future__ import annotations

import os
from pathlib import Path

import psutil
import win32com.client
from loguru import logger
from win32comext.shell import shell as win32shell
from win32comext.shell import shellcon as win32shellcon


def kill_process(name: str, force: bool = False, wait: bool = False, timeout: float = 1.0) -> None:
    """终止进程

    Args:
        name (str): 进程名
        force (bool, optional): 强制终止进程
        wait (bool, optional): 等待进程结束（阻塞）
    """
    for process in psutil.process_iter(["name"]):
        if process.info["name"] == f"{name}.exe":
            try:
                if force:
                    process.kill()
                else:
                    process.terminate()
                logger.info(f"已向进程 {name} 发送{'强行' if force else ''}终止信号{', 等待中……' if wait else ''}")

                if wait:
                    try:
                        process.wait(timeout)
                        logger.info(f"成功关闭进程 {name}")
                    except psutil.TimeoutExpired:
                        logger.warning(f"进程 {name} 关闭超时")
            except psutil.NoSuchProcess:
                logger.warning(f"进程 {name} 已不存在")
            except psutil.AccessDenied:
                logger.warning("访问被拒绝, 回退至 taskkill")
                if force:
                    os.system(f'taskkill /f /im "{name}.exe" >nul 2>&1')
                else:
                    os.system(f'taskkill /im "{name}.exe" >nul 2>&1')


def probe_ci_executable() -> Path | None:
    """探测 ClassIsland 可执行文件位置

    依次探测启动目录、用户开始菜单、桌面（用户与公共）中的快捷方式。
    """
    folders = [
        ("启动目录", win32shellcon.CSIDL_STARTUP),
        ("开始菜单程序", win32shellcon.CSIDL_PROGRAMS),
        ("开始菜单", win32shellcon.CSIDL_STARTMENU),
        ("桌面", win32shellcon.CSIDL_DESKTOPDIRECTORY),
        ("公共桌面", win32shellcon.CSIDL_COMMON_DESKTOPDIRECTORY),
    ]

    try:
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception as e:
        logger.error(f"初始化 WScript.Shell 时出错: {e}")
        return None

    for label, csidl in folders:
        lnk_path = Path(win32shell.SHGetFolderPath(0, csidl, 0, 0)) / "ClassIsland.lnk"
        if not lnk_path.exists():
            continue

        try:
            # 解析快捷方式
            target = Path(shell.CreateShortcut(str(lnk_path)).TargetPath).resolve()
        except Exception as e:
            logger.warning(f"解析 {label} 快捷方式失败 {lnk_path}: {e}")
            continue

        if target.exists():
            logger.info(f"通过快捷方式 {lnk_path} 定位到 ClassIsland: {target}")
            return target

    logger.warning("未能在常用位置找到 ClassIsland")
    return None
