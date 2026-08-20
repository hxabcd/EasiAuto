import json
import time
from pathlib import Path

from loguru import logger

from EasiAuto.automation.easinote_api import (
    SeewoAuthError,
    SeewoClient,
    SeewoLoginError,
    SeewoNeedCaptcha,
    SeewoNetworkError,
)
from EasiAuto.automation.easinote_patcher import PIPE_NAME, fetch_current_login_info
from EasiAuto.models import config

from .base import BaseAutomator, LoginError


class TokenAutomator(BaseAutomator):
    def __init__(self, account: str, password: str) -> None:
        super().__init__(account, password)

        self.seewo_client = SeewoClient()
        try:
            self.login_info = self.seewo_client.login(account, password)
        except SeewoNetworkError as e:
            raise LoginError("网络异常", retry=True) from e
        except SeewoAuthError as e:
            raise LoginError("账号或密码错误", retry=False) from e
        except SeewoNeedCaptcha as e:
            raise LoginError("账号被风控", retry=False) from e
        except SeewoLoginError as e:
            raise LoginError("未知登录异常", retry=False) from e

    def check_logged_in(self) -> bool:
        info = fetch_current_login_info(False)
        if info and info.get("statusCode") == 202:
            current_uid = info.get("userId", "")
            return current_uid and current_uid == self.login_info.user.uid
        return False

    def prepare(self):
        if not config.Internal.IsEasiNotePatched:
            raise LoginError("希沃白板未修补", retry=False)
        return super().prepare()

    def login(self) -> None:
        login_payload = {
            "statusCode": 202,
            "token": self.login_info.token,
            "userId": self.login_info.user.uid,
            "userName": self.login_info.user.username,
            "nickName": self.login_info.user.nick_name,
            "phone": self.login_info.user.phone,
            "result": "https://e.seewo.com",
            "message": "客户端已扫码并确认登录",
        }

        json_data = json.dumps(login_payload, ensure_ascii=False)
        logger.info(f"[IPC] 准备通过管道投递令牌, userId={self.login_info.user.uid}")

        self.update_progress("准备投递令牌")
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            self.check_interruption()
            try:
                with Path(PIPE_NAME).open("r+", encoding="utf-8") as pipe:
                    pipe.write(json_data + "\n")
                    pipe.flush()
                    response_line = pipe.readline().strip()
                if not response_line:
                    raise OSError("管道未返回响应")

                try:
                    response = json.loads(response_line)
                except json.JSONDecodeError as e:
                    raise LoginError("登录管道返回无效响应", retry=False) from e

                if response.get("Success"):
                    logger.info(f"[IPC] 登录成功: {response.get('Message', '')}")
                    self.update_progress("登录完成")
                    return

                err_msg = response.get("Message") or "未知错误"
                err_detail = response.get("ErrorDetail") or ""
                error_code = response.get("Code") or response.get("ErrorCode") or response.get("errorCode")
                if str(error_code) == "4000" or "4000" in f"{err_detail}{err_msg}":
                    raise LoginError("令牌已失效，请重新获取", retry=False)
                logger.error(f"[IPC] 登录失败: {err_msg} ({err_detail})")
                raise LoginError(f"令牌登录失败: {err_msg}")
            except LoginError:
                raise
            except FileNotFoundError:
                logger.debug(f"[IPC] 管道尚未就绪, 第 {attempt}/{max_retries} 次重试...")
                self.update_progress(f"等待管道就绪 ({attempt}/{max_retries})")
            except OSError as e:
                logger.debug(f"[IPC] 管道未就绪: {e}, 第 {attempt}/{max_retries} 次重试...")

            if attempt < max_retries:
                self.check_interruption()
                time.sleep(1)

        raise LoginError("登录管道未启动，请检查希沃白板修补状态", retry=False)
