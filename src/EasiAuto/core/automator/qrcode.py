import json
import time

from loguru import logger

from EasiAuto.models import config

from .base import BaseAutomator, LoginError

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


class QrCodeAutomator(BaseAutomator):
    def __init__(self, token_data: dict) -> None:
        super().__init__(account="", password="")
        self._token_data = token_data
        self._target_user_id = token_data.get("userId", "")

    def check_logged_in(self) -> bool:
        info = fetch_current_login_info(False)
        if info and info.get("statusCode") == 202:
            current_uid = info.get("userId", "")
            return current_uid and current_uid == self._target_user_id
        return False

    def prepare(self):
        if not config.Internal.IsEasiNotePatched:
            raise LoginError("希沃白板未修补", retry=False)
        return super().prepare()

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
