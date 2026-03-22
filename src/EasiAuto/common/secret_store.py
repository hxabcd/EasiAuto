from __future__ import annotations

import ctypes
from pathlib import Path

from cryptography.fernet import Fernet
from loguru import logger

from EasiAuto.common.consts import EA_DATADIR

SERVICE_NAME = "EasiAuto"
KEY_USERNAME = "profile"
KEY_FILE = EA_DATADIR / "profile.key"
KEY_CACHE: bytes | None = None


def read_key() -> str | None:
    path = Path(KEY_FILE)
    if not path.exists():
        return None

    key = path.read_text(encoding="ascii").strip()
    if not key:
        return None
    return key


def write_key(key: str) -> None:
    path = Path(KEY_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key, encoding="ascii")

    # 隐藏
    ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)


def get_key() -> bytes:
    """从本地文件读取密钥；不存在时自动生成并写入。"""
    global KEY_CACHE

    if KEY_CACHE is not None:
        return KEY_CACHE

    try:
        key = read_key()
    except Exception as e:
        raise RuntimeError("读取本地密钥文件失败，无法获取档案密钥") from e

    if not key:
        key = Fernet.generate_key().decode("ascii")
        try:
            write_key(key)
        except Exception as e:
            raise RuntimeError("写入本地密钥文件失败，无法保存档案密钥") from e
        logger.info("首次运行已生成档案密钥并写入本地文件")

    KEY_CACHE = key.encode("ascii")
    return KEY_CACHE


def get_profile_cipher() -> Fernet:
    return Fernet(get_key())
