from __future__ import annotations

import hashlib
from io import BytesIO

import requests
from loguru import logger
from PIL import Image

from PySide6.QtCore import QThread, Signal

from EasiAuto.automation.easinote_api import (
    SeewoAuthError,
    SeewoClient,
    SeewoLoginError,
    SeewoNeedCaptcha,
    SeewoNetworkError,
)
from EasiAuto.consts import AVATAR_DIR


class UserAuthVerificationThread(QThread):
    """后台线程：校验希沃账号密码，并缓存头像。"""

    succeeded = Signal(str, str, str)  # account_name, avatar_path, uid
    failed = Signal(str)  # 认证失败原因
    offline = Signal(str)  # 网络异常（跳过校验）

    def __init__(self, account: str, password: str, parent=None):
        super().__init__(parent)
        self._account = account
        self._password = password

    def run(self) -> None:
        try:
            with SeewoClient() as client:
                result = client.login(self._account, self._password)
        except SeewoNetworkError as e:
            self.offline.emit(str(e))
            return
        except SeewoNeedCaptcha as e:
            self.failed.emit(str(e))
            return
        except (SeewoAuthError, SeewoLoginError) as e:
            self.failed.emit(str(e))
            return

        avatar_path = self._download_avatar(result.user.photo_url or None)
        account_name = result.user.nick_name or result.user.real_name
        self.succeeded.emit(account_name, avatar_path or "", result.user.uid)

    @staticmethod
    def _download_avatar(url: str | None) -> str | None:
        """下载头像到本地缓存并返回文件路径，失败或不存在返回 None"""
        if not url:
            return None
        try:
            response = requests.get(url, timeout=15)
            if response.status_code != 200:
                return None
            image = Image.open(BytesIO(response.content))
            image.load()
        except Exception as e:
            logger.warning(f"头像下载失败: {e}")
            return None

        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = AVATAR_DIR / f"{hashlib.md5(url.encode('utf-8')).hexdigest()}.png"
        try:
            image.save(cache_path, format="PNG")
        except OSError as e:
            logger.warning(f"头像保存失败: {e}")
            return None
        return str(cache_path)
