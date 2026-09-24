"""希沃白板进程控制：终止既有实例与按参数启动

只包含与进程交互的机制，不含重试策略与界面反馈。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger

from EasiAuto.core.process import kill_process


def kill_targets(process_name: str, *, kill_agent: bool, extra_kills: str, timeout: float) -> None:
    """终止希沃白板及其附属进程

    Args:
        process_name (str): 希沃白板进程名
        kill_agent (bool): 是否一并终止 EasiAgent 服务
        extra_kills (str): 额外需要终止的进程名，以英文逗号分隔
        timeout (float): 每个进程终止后的等待时长（秒）
    """
    target_list: list[str] = [process_name]
    if kill_agent:
        target_list.append("EasiAgent")
    if extra_kills:
        target_list += extra_kills.split(",")

    targets = [target.strip().removesuffix(".exe") for target in target_list]
    logger.debug(f"要终止的目标进程: {', '.join(targets)}")

    for target in targets:
        kill_process(target, force=True, wait=True, timeout=timeout)


def launch(executable: Path, args: str) -> subprocess.Popen:
    """启动希沃白板

    Args:
        executable (Path): 启动器可执行文件路径
        args (str): 启动参数，按空白字符分隔

    Returns:
        subprocess.Popen: 已启动的进程句柄

    Raises:
        OSError: 启动失败（文件缺失、权限不足等）
    """
    logger.debug(f"路径: {executable}, 参数: {args}")
    return subprocess.Popen([str(executable.resolve()), *args.split()])
