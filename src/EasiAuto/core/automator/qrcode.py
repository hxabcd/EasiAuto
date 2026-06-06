from __future__ import annotations

import json
import time

from loguru import logger

from .base import BaseAutomator, LoginError

PIPE_NAME = r"\\.\pipe\SeewoOpenTokenPipe"


class QRCodeAutomator(BaseAutomator):

    def __init__(self, account: str, password: str, token_data: dict | None = None) -> None:
        super().__init__(account, password)
        self._token_data = token_data or {}

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
                with open(PIPE_NAME, "w", encoding="utf-8") as pipe:
                    pipe.write(json_data + "\n")
                    pipe.flush()
                logger.info("[IPC] 令牌投递成功")
                self.update_progress("令牌已投递, 等待登录完成")
                time.sleep(2)
                return
            except FileNotFoundError:
                logger.debug(f"[IPC] 管道尚未就绪, 第 {attempt}/{max_retries} 次重试...")
                self.update_progress(f"等待管道就绪 ({attempt}/{max_retries})")
                time.sleep(1)
            except OSError as e:
                logger.warning(f"[IPC] 管道写入异常: {e}")
                time.sleep(1)

        raise LoginError(f"命名管道 {PIPE_NAME} 在 {max_retries} 次尝试内未能就绪")
