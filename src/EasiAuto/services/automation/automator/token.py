import time

from loguru import logger

from EasiAuto.integrations.easinote import pipe
from EasiAuto.integrations.easinote.api import (
    SeewoAuthError,
    SeewoClient,
    SeewoLoginError,
    SeewoNeedCaptcha,
    SeewoNetworkError,
)
from EasiAuto.integrations.easinote.patcher import is_patched

from .base import BaseAutomator
from .errors import LoginError

# 等待白板管道就绪的最大尝试次数与重试间隔
PIPE_ATTEMPTS = 2
PIPE_RETRY_DELAY = 1.0


class TokenAutomator(BaseAutomator):
    def check_logged_in(self) -> bool:
        if not is_patched():
            return False
        return self._current_uid() == self.login_info.user.uid

    def before_prepare(self):
        if not is_patched():
            raise LoginError("希沃白板未修补", retry=False)

        self.seewo_client = SeewoClient()
        try:
            self.login_info = self.seewo_client.login(self.account, self.password)
        except SeewoNetworkError as e:
            raise LoginError("网络异常", retry=True) from e
        except SeewoAuthError as e:
            raise LoginError("账号或密码错误", retry=False) from e
        except SeewoNeedCaptcha as e:
            raise LoginError("账号被风控", retry=False) from e
        except SeewoLoginError as e:
            raise LoginError("未知登录异常", retry=False) from e

    def _build_payload(self) -> pipe.TokenPayload:
        """把希沃 API 登录结果转换为管道载荷"""
        user = self.login_info.user
        return pipe.TokenPayload(
            token=self.login_info.token,
            user_id=user.uid,
            user_name=user.username,
            nick_name=user.nick_name,
            phone=user.phone,
        )

    def _handle_response(self, response: pipe.TokenResponse) -> None:
        """按回执判定投递结果

        Raises:
            LoginError: 回执表示投递失败
        """
        if response.success:
            logger.info(f"[IPC] 登录成功: {response.message}")
            self.update_progress("登录完成")
            return

        # 回执可能不带 Message，保留可读的兜底文案
        message = response.message or "未知错误"
        if response.token_expired:
            logger.error(f"[IPC] 令牌已失效: {message} ({response.error_detail})")
            raise LoginError("令牌已失效，请重新获取", retry=False)

        logger.error(f"[IPC] 登录失败: {message} ({response.error_detail})")
        raise LoginError(f"令牌登录失败: {message}")

    def login(self) -> None:
        payload = self._build_payload()
        logger.info(f"[IPC] 准备通过管道投递令牌, userId={payload.user_id}")
        self.update_progress("准备投递令牌")

        message = payload.to_json()
        for attempt in range(1, PIPE_ATTEMPTS + 1):
            self.check_interruption()
            try:
                line = pipe.send_and_read(pipe.TOKEN_PIPE, message)
            except pipe.PipeDeniedError as e:
                # 权限不足重试无意义，直接失败
                raise LoginError(f"管道访问被拒绝（权限不足）: {e}", retry=False) from e
            except pipe.PipeUnavailableError as e:
                logger.debug(f"[IPC] 管道尚未就绪: {e}, 第 {attempt}/{PIPE_ATTEMPTS} 次尝试")
                self.update_progress(f"等待管道就绪 ({attempt}/{PIPE_ATTEMPTS})")
            else:
                try:
                    response = pipe.TokenResponse.parse(line)
                except ValueError as e:
                    raise LoginError("登录管道返回无效响应", retry=False) from e
                self._handle_response(response)
                return

            if attempt < PIPE_ATTEMPTS:
                self.check_interruption()
                time.sleep(PIPE_RETRY_DELAY)

        raise LoginError("登录管道未启动，请检查希沃白板修补状态", retry=False)
