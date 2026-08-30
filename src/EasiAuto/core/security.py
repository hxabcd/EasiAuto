"""安全工具：主密码派生与档案加密

档案加密使用用户设置的主密码（Argon2id 派生密钥），
密码正确性通过档案内保存的校验密文验证。

解锁密钥缓存：解锁后用 Windows DPAPI 按当前用户加密派生密钥，
写入本机缓存文件，供自动登录与「免密查看档案」使用。
"""

from __future__ import annotations

import base64
import ctypes
from contextlib import suppress

import win32crypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from EasiAuto.consts import EA_DATADIR

# 旧版机器密钥文件路径（仅用于 v3 及更早版本的档案迁移）
LEGACY_KEY_FILE = EA_DATADIR / "profile.key"

# 解锁密钥缓存：按当前 Windows 用户 DPAPI 加密保存的派生密钥
UNLOCK_CACHE_FILE = EA_DATADIR / "profile.unlock"

# 主密码 KDF（Argon2id）参数：内存 64 MiB、3 次迭代、4 路并行
ARGON2_MEMORY_COST = 65536
ARGON2_ITERATIONS = 3
ARGON2_LANES = 4


class _MasterKeyState:
    """会话内主密码密钥缓存"""

    def __init__(self):
        self._key: bytes | None = None

    def set(self, key: bytes) -> None:
        self._key = key

    def get(self) -> bytes | None:
        return self._key

    def clear(self) -> None:
        self._key = None


_state = _MasterKeyState()


def derive_master_key(master_password: str, salt: bytes) -> bytes:
    """使用 Argon2id 从主密码与盐值派生 Fernet 密钥。"""
    kdf = Argon2id(
        salt=salt,
        length=32,
        iterations=ARGON2_ITERATIONS,
        lanes=ARGON2_LANES,
        memory_cost=ARGON2_MEMORY_COST,
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode("utf-8")))


def unlock_master_key(master_password: str, salt: bytes) -> None:
    """解锁主密码：派生密钥并缓存，后续加密/解密均以该密钥为准。"""
    _state.set(derive_master_key(master_password, salt))


def lock_master_key() -> None:
    """清除当前会话缓存的主密码密钥。"""
    _state.clear()


def is_master_key_unlocked() -> bool:
    """主密码是否已解锁（当前会话可进行档案加解密）。"""
    return _state.get() is not None


def set_master_key(key: bytes) -> None:
    """直接设置当前会话密钥（用于启动时从本机缓存自动解锁）。"""
    _state.set(key)


def get_master_key() -> bytes | None:
    """获取当前会话的派生密钥；未解锁时返回 None。"""
    return _state.get()


def _dpapi_protect(data: bytes) -> bytes:
    """用 Windows DPAPI 按当前用户加密数据。"""
    return win32crypt.CryptProtectData(data)


def _dpapi_unprotect(blob: bytes) -> bytes:
    """用 Windows DPAPI 解密本机缓存数据。"""
    return win32crypt.CryptUnprotectData(blob)[1]


def cache_master_key(key: bytes) -> None:
    """把派生密钥用 DPAPI 加密写入本机解锁缓存。"""
    UNLOCK_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 清除已有文件的只读/隐藏属性，避免覆盖写入失败
    with suppress(OSError):
        ctypes.windll.kernel32.SetFileAttributesW(str(UNLOCK_CACHE_FILE), 0x80)
    UNLOCK_CACHE_FILE.write_bytes(_dpapi_protect(key))
    ctypes.windll.kernel32.SetFileAttributesW(str(UNLOCK_CACHE_FILE), 0x02)  # 隐藏


def clear_cached_key() -> None:
    """删除本机解锁缓存（关闭加密时调用）。"""
    with suppress(OSError):
        ctypes.windll.kernel32.SetFileAttributesW(str(UNLOCK_CACHE_FILE), 0x80)
    with suppress(OSError):
        UNLOCK_CACHE_FILE.unlink(missing_ok=True)


def read_cached_key() -> bytes | None:
    """读取本机解锁缓存中的派生密钥；不可用或无缓存时返回 None。"""
    try:
        blob = UNLOCK_CACHE_FILE.read_bytes()
    except OSError:
        return None
    if not blob:
        return None
    try:
        return _dpapi_unprotect(blob)
    except Exception:
        return None


def get_profile_cipher() -> Fernet:
    """获取档案加解密器；主密码未解锁时抛出 RuntimeError。"""
    key = _state.get()
    if key is None:
        raise RuntimeError("主密码未解锁，无法访问档案密钥")
    return Fernet(key)


def get_legacy_cipher() -> Fernet | None:
    """读取旧版机器密钥文件生成加解密器（仅用于档案迁移）；不存在时返回 None。"""
    try:
        key = LEGACY_KEY_FILE.read_text(encoding="ascii").strip()
    except OSError:
        return None
    if not key:
        return None
    return Fernet(key.encode("ascii"))
