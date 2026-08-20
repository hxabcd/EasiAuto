"""希沃白板 DLL 修补模块 — 部署 DLL 并通过 DllPatcher 修补 EasiNote.Account.dll"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from loguru import logger

from EasiAuto.consts import VENDOR_PATH

# cmd_patch 专用退出码，值 20–29 与系统中其他退出码（0/1/2/argparse 的 2）完全隔离
PATCH_OK = 20
PATCH_ERR_OPERATION_FAILED = 21
PATCH_ERR_EASINOTE_NOT_FOUND = 22
PATCH_ERR_UNKNOWN = 29


def _deploy_file(src: Path, dst: Path) -> bool:
    """哈希一致跳过，不一致则 .bak 备份后覆盖。返回 True 表示成功或无需操作。"""
    if not src.exists():
        logger.warning(f"源文件不存在: {src}")
        return False

    if dst.exists():
        try:
            if src.read_bytes() == dst.read_bytes():
                logger.debug(f"文件内容一致，跳过: {dst.name}")
                return True
        except OSError as e:
            logger.error(f"读取文件失败: {e}")
            return False

        backup = dst.with_suffix(dst.suffix + ".bak")
        logger.info(f"创建备份: {backup}")
        try:
            shutil.move(dst, backup)
        except OSError as e:
            logger.error(f"备份失败: {dst} -> {backup}，{e}")
            return False

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except OSError as e:
        logger.error(f"写入失败: {dst}，{e}")
        return False

    logger.success(f"已部署: {dst}")
    return True


def _find_easinote_version_dirs(base_dir: Path) -> list[Path]:
    """查找所有 EasiNote5_*/Main 子目录"""
    dirs: list[Path] = []
    if not base_dir.exists():
        return dirs
    try:
        children = list(base_dir.iterdir())
    except OSError as e:
        logger.error(f"扫描目录失败: {base_dir}，{e}")
        return dirs

    for child in children:
        if child.is_dir() and child.name.startswith("EasiNote5_"):
            main_dir = child / "Main"
            if main_dir.exists():
                dirs.append(main_dir)
    return dirs


def _is_newtonsoft_patched(dll_path: Path) -> bool:
    """检测 DLL 是否包含 SeewoPipeBridge 引用"""
    try:
        return b"SeewoPipeBridge" in dll_path.read_bytes()
    except Exception:
        return False


def _is_account_patched(dll_path: Path) -> bool:
    try:
        data = dll_path.read_bytes()
        return b"IsTokenLoggedByProcess" in data and b"StartBridge" in data
    except OSError:
        return False


def is_easinote_patched(easinote_exe_path: Path) -> bool:
    easinote_base = easinote_exe_path.parent.parent.resolve()
    target_dirs = _find_easinote_version_dirs(easinote_base)
    if not target_dirs:
        return False
    return all(
        (main_dir / "SeewoPipeBridge.dll").exists()
        and _is_account_patched(main_dir / "EasiNote.Account.dll")
        for main_dir in target_dirs
    )


def patch_easinote(easinote_exe_path: Path) -> bool:
    dllpatcher_exe = VENDOR_PATH / "DllPatcher" / "DllPatcher.exe"

    easinote_base = easinote_exe_path.parent.parent.resolve()
    target_dirs = _find_easinote_version_dirs(easinote_base)
    if not target_dirs:
        logger.warning(f"无法在 {easinote_base} 找到希沃白板版本目录")
        return False

    logger.info(f"找到 {len(target_dirs)} 个目标目录")
    all_patched = True

    # 仅需部署 SeewoPipeBridge.dll；Newtonsoft.Json.dll 由 DllPatcher 直接处理
    deploy_dlls = ["SeewoPipeBridge.dll"]

    for main_dir in target_dirs:
        logger.info(f"处理: {main_dir}")

        newtonsoft_dll = main_dir / "Newtonsoft.Json.dll"
        newtonsoft_bak = main_dir / "Newtonsoft.Json.dll.bak"
        if newtonsoft_dll.exists() and newtonsoft_bak.exists():
            if _is_newtonsoft_patched(newtonsoft_dll):
                logger.warning("检测到 Newtonsoft.Json.dll 已被注入，从备份恢复")
                try:
                    shutil.copy2(newtonsoft_bak, newtonsoft_dll)
                except OSError as e:
                    logger.error(f"恢复失败: {newtonsoft_dll}，{e}")
                    all_patched = False
                    continue

        for dll_name in deploy_dlls:
            if not _deploy_file(VENDOR_PATH / dll_name, main_dir / dll_name):
                all_patched = False

        if not dllpatcher_exe.exists():
            logger.warning("DllPatcher 不可用")
            all_patched = False
            continue

        target_dll = main_dir / "EasiNote.Account.dll"
        if not target_dll.exists():
            logger.debug(f"跳过不存在的: {target_dll}")
            continue

        try:
            result = subprocess.run(
                [str(dllpatcher_exe), str(target_dll)],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"DllPatcher 超时: {target_dll}")
            all_patched = False
            continue
        except OSError as e:
            logger.error(f"运行 DllPatcher 失败: {dllpatcher_exe}，{e}")
            all_patched = False
            continue

        if result.returncode == 0:
            logger.success(f"已修补: {target_dll}")
        else:
            logger.warning(f"修补失败: {target_dll}\n{result.stderr or '(无错误输出)'}")
            all_patched = False

    return all_patched


def _restore_from_bak(file_path: Path) -> bool:
    bak = file_path.with_suffix(file_path.suffix + ".bak")
    if not bak.exists():
        return False
    logger.info(f"从备份恢复: {file_path}")
    try:
        shutil.copy2(bak, file_path)
        bak.unlink()
        return True
    except OSError as e:
        logger.error(f"恢复失败: {file_path}，{e}")
        return False


def unpatch_easinote(easinote_exe_path: Path) -> bool:
    easinote_base = easinote_exe_path.parent.parent.resolve()
    target_dirs = _find_easinote_version_dirs(easinote_base)
    if not target_dirs:
        logger.warning(f"无法在 {easinote_base} 找到希沃白板版本目录")
        return False

    logger.info(f"找到 {len(target_dirs)} 个目标目录")
    all_unpatched = True

    for main_dir in target_dirs:
        logger.info(f"处理: {main_dir}")

        pipe_bridge = main_dir / "SeewoPipeBridge.dll"
        if pipe_bridge.exists():
            logger.info(f"移除: {pipe_bridge.name}")
            try:
                pipe_bridge.unlink()
            except OSError as e:
                logger.error(f"移除失败: {pipe_bridge}，{e}")
                all_unpatched = False
                continue

        newtonsoft_dll = main_dir / "Newtonsoft.Json.dll"
        if newtonsoft_dll.exists() and _is_newtonsoft_patched(newtonsoft_dll):
            if not _restore_from_bak(newtonsoft_dll):
                logger.warning(f"{newtonsoft_dll.name} 已被修改但无备份可用")
                all_unpatched = False

        account_dll = main_dir / "EasiNote.Account.dll"
        account_bak = main_dir / "EasiNote.Account.dll.bak"
        if account_dll.exists() and account_bak.exists():
            if not _restore_from_bak(account_dll):
                logger.warning(f"恢复 {account_dll.name} 失败")
                all_unpatched = False

    return all_unpatched


PIPE_NAME = r"\\.\pipe\SeewoOpenTokenPipe"
LOGIN_INFO_PIPE = r"\\.\pipe\SeewoLoginInfoPipe"


def fetch_current_login_info(add_to_logged_tokens: bool = False) -> dict | None:
    """从 SeewoLoginInfoPipe 获取当前已登录账户信息"""
    try:
        with open(LOGIN_INFO_PIPE, "r+", encoding="utf-8") as pipe:
            pipe.write(str(add_to_logged_tokens).lower() + "\n")
            pipe.flush()
            return json.loads(pipe.readline())
    except Exception:
        return None
