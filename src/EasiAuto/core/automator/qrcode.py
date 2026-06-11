from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import winreg
from pathlib import Path

import psutil
from loguru import logger

from EasiAuto.consts import VENDOR_PATH

from .base import BaseAutomator, LoginError

PIPE_NAME = r"\\.\pipe\SeewoOpenTokenPipe"
LOGIN_INFO_PIPE = r"\\.\pipe\SeewoLoginInfoPipe"


def fetch_current_login_info() -> dict | None:
    """从 SeewoLoginInfoPipe 获取当前已登录账户信息"""
    try:
        with open(LOGIN_INFO_PIPE, "r", encoding="utf-8") as pipe:
            return json.loads(pipe.readline())
    except Exception:
        return None


def _file_sha1(path: Path) -> str:
    sha1 = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha1.update(chunk)
    return sha1.hexdigest()


def _deploy_file(src: Path, dst: Path):
    if not src.exists():
        logger.warning(f"源文件不存在: {src}")
        return

    if dst.exists():
        if _file_sha1(src) == _file_sha1(dst):
            logger.debug(f"哈希一致，跳过: {dst.name}")
            return
        backup = dst.with_suffix(dst.suffix + ".bak")
        logger.info(f"创建备份: {backup}")
        shutil.move(dst, backup)

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    logger.success(f"已部署: {dst}")


def _find_easinote_version_dirs(base_dir: Path) -> list[Path]:
    dirs = []
    if not base_dir.exists():
        return dirs
    for child in base_dir.iterdir():
        if child.is_dir() and child.name.startswith("EasiNote5_"):
            main_dir = child / "Main"
            if main_dir.exists():
                dirs.append(main_dir)
    return dirs


def _kill_processes_holding_file(file_path: str):
    killed = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            for mmap in proc.memory_maps():
                if file_path.lower() in mmap.path.lower():
                    proc.kill()
                    killed.add(proc.info["name"])
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    for name in killed:
        logger.info(f"已终止占用 DLL 的进程: {name}")

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with open(file_path, "r+b"):
                logger.debug("DLL 已解除占用")
                return
        except OSError:
            time.sleep(0.5)
    logger.warning(f"DLL 等待解除占用超时: {file_path}")


def deploy_resources():
    dllpatcher_exe = VENDOR_PATH / "DllPatcher" / "DllPatcher.exe"

    easinote_base = None
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Seewo\EasiNote5",
        ) as key:
            exe_path = Path(winreg.QueryValueEx(key, "ExePath")[0])
            easinote_base = exe_path.parent.parent.resolve()
    except Exception:
        pass

    if easinote_base is None:
        easinote_base = Path(r"C:\Program Files (x86)\Seewo\EasiNote5")

    target_dirs = _find_easinote_version_dirs(easinote_base)
    if not target_dirs:
        logger.warning(f"未找到 EasiNote5_* 目录在: {easinote_base}")
        return

    logger.info(f"找到 {len(target_dirs)} 个目标目录")

    deploy_dlls = ["Newtonsoft.Json.dll", "SeewoPipeBridge.dll"]

    for main_dir in target_dirs:
        logger.info(f"处理: {main_dir}")
        for dll_name in deploy_dlls:
            _deploy_file(VENDOR_PATH / dll_name, main_dir / dll_name)

        if dllpatcher_exe.exists():
            target_dll = main_dir / "EasiNote.Account.dll"
            if target_dll.exists():
                _kill_processes_holding_file(str(target_dll))
                result = subprocess.run(
                    [str(dllpatcher_exe), str(target_dll)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    logger.success(f"已修补: {target_dll}")
                else:
                    logger.warning(f"修补失败: {target_dll}\n{result.stderr}")
            else:
                logger.debug(f"跳过不存在的: {target_dll}")
        else:
            logger.warning("DllPatcher 不可用")


class QRCodeAutomator(BaseAutomator):
    def __init__(self, token_data: dict) -> None:
        super().__init__(account="", password="")
        self._token_data = token_data
        self._target_user_id = token_data.get("userId", "")

    def _after_easinote_dead(self):
        deploy_resources()

    def login(self) -> None:
        token = self._token_data.get("token", "")
        user_id = self._token_data.get("userId", "")
        nick_name = self._token_data.get("nickName", "")
        phone = self._token_data.get("phone", "")

        if not token:
            raise LoginError("登录令牌 (token) 为空, 无法进行 IPC 投递")

        login_payload = {
            "statusCode": 202,
            "token": token,
            "userId": user_id,
            "userName": nick_name,
            "nickName": nick_name,
            "phone": phone,
            "result": "https://e.seewo.com",
            "message": "客户端已扫码并确认登录",
        }

        json_data = json.dumps(login_payload, ensure_ascii=False)
        logger.info(f"[IPC] 准备通过管道投递令牌, userId={user_id}")

        self.update_progress("等待希沃白板登录窗口就绪")
        max_retries = 15
        for attempt in range(1, max_retries + 1):
            self.check_interruption()
            try:
                with open(PIPE_NAME, "r+", encoding="utf-8") as pipe:
                    pipe.write(json_data + "\n")
                    pipe.flush()
                    response_line = pipe.readline()
                    if response_line:
                        response = json.loads(response_line)
                        if response.get("Success"):
                            logger.info(f"[IPC] 登录成功: {response.get('Message', '')}")
                            self.update_progress("登录完成")
                            time.sleep(1)
                            return
                        else:
                            err_msg = response.get("Message", "未知错误")
                            err_detail = response.get("ErrorDetail", "")
                            logger.error(f"[IPC] 登录失败: {err_msg} ({err_detail})")
                            raise LoginError(f"管道登录失败: {err_msg}")
                logger.warning("[IPC] 未收到响应，重试...")
            except LoginError:
                raise
            except FileNotFoundError:
                logger.debug(f"[IPC] 管道尚未就绪, 第 {attempt}/{max_retries} 次重试...")
                self.update_progress(f"等待管道就绪 ({attempt}/{max_retries})")
                time.sleep(1)
            except OSError as e:
                logger.debug(f"[IPC] 管道未就绪: {e}, 第 {attempt}/{max_retries} 次重试...")
                time.sleep(1)

        raise LoginError(f"命名管道 {PIPE_NAME} 在 {max_retries} 次尝试内未能就绪")
