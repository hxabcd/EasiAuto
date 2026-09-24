"""希沃白板命名管道协议

与希沃白板内嵌的 SeewoPipeBridge 配合工作，负责与修补后的白板交换登录令牌与登录态：

- ``TOKEN_PIPE``：投递登录令牌，等待白板回执
- ``LOGIN_INFO_PIPE``：查询白板当前的登录账号

只承载传输与协议模型，重试次数等策略由调用方（登录策略）决定。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

TOKEN_PIPE = r"\\.\pipe\SeewoOpenTokenPipe"
LOGIN_INFO_PIPE = r"\\.\pipe\SeewoLoginInfoPipe"


class PipeUnavailableError(Exception):
    """管道未就绪或未返回内容，属于可重试错误"""


class PipeDeniedError(Exception):
    """管道访问被拒绝（权限不足），重试无意义"""


@dataclass(slots=True, frozen=True)
class TokenPayload:
    """投递给希沃白板的登录令牌载荷，字段名与 SeewoPipeBridge 约定一致"""

    token: str
    user_id: str
    user_name: str
    nick_name: str
    phone: str
    status_code: int = 202
    result: str = "https://e.seewo.com"
    message: str = "客户端已扫码并确认登录"

    def to_json(self) -> str:
        return json.dumps(
            {
                "statusCode": self.status_code,
                "token": self.token,
                "userId": self.user_id,
                "userName": self.user_name,
                "nickName": self.nick_name,
                "phone": self.phone,
                "result": self.result,
                "message": self.message,
            },
            ensure_ascii=False,
        )


@dataclass(slots=True, frozen=True)
class TokenResponse:
    """白板对令牌投递的回执"""

    success: bool
    message: str = ""
    error_detail: str = ""
    code: str | None = None

    @property
    def token_expired(self) -> bool:
        """回执是否表示令牌已失效（需重新获取令牌）"""
        return self.code == "4000" or "4000" in f"{self.error_detail}{self.message}"

    @classmethod
    def parse(cls, line: str) -> TokenResponse:
        """解析回执行

        Raises:
            ValueError: 回执不是合法的 JSON 对象
        """
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"回执不是合法 JSON: {line!r}") from e
        if not isinstance(data, dict):
            raise ValueError(f"回执不是 JSON 对象: {line!r}")

        code = data.get("Code") or data.get("ErrorCode") or data.get("errorCode")
        return cls(
            success=bool(data.get("Success")),
            message=str(data.get("Message") or ""),
            error_detail=str(data.get("ErrorDetail") or ""),
            code=str(code) if code is not None else None,
        )


@dataclass(slots=True, frozen=True)
class CurrentLoginInfo:
    """白板当前登录态（SeewoLoginInfoPipe 返回值）"""

    status_code: int = 0
    user_id: str = ""
    token: str = ""
    user_name: str = ""
    nick_name: str = ""
    phone: str = ""
    message: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def is_logged_in(self) -> bool:
        """白板当前是否处于已登录状态"""
        return self.status_code == 202


def send_and_read(pipe_name: str, message: str) -> str:
    """向命名管道写入一行消息并读取一行回执

    Args:
        pipe_name (str): 管道全路径，如 ``TOKEN_PIPE``
        message (str): 单行消息内容（不含换行符）

    Returns:
        str: 回执行内容（已去除首尾空白）

    Raises:
        PipeUnavailableError: 管道不存在、被占用或未返回内容
        PipeDeniedError: 权限不足
    """
    try:
        with Path(pipe_name).open("r+", encoding="utf-8") as pipe:
            pipe.write(message + "\n")
            pipe.flush()
            line = pipe.readline().strip()
    except PermissionError as e:
        raise PipeDeniedError(str(e)) from e
    except OSError as e:
        raise PipeUnavailableError(str(e)) from e

    if not line:
        raise PipeUnavailableError("管道未返回响应")
    return line


def read_current_login_info(add_to_logged_tokens: bool = False) -> CurrentLoginInfo | None:
    """查询白板当前登录态

    Args:
        add_to_logged_tokens (bool, optional): 是否让白板把当前令牌加入已登录令牌表

    Returns:
        CurrentLoginInfo | None: 解析结果；管道不可用或响应异常时为 None
    """
    try:
        line = send_and_read(LOGIN_INFO_PIPE, str(add_to_logged_tokens).lower())
    except (PipeUnavailableError, PipeDeniedError) as e:
        logger.debug(f"[IPC] 登录信息管道不可用: {e}")
        return None

    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        logger.debug(f"[IPC] 登录信息管道返回无效响应: {e}")
        return None
    if not isinstance(data, dict):
        logger.debug(f"[IPC] 登录信息管道返回非对象响应: {line!r}")
        return None

    try:
        status_code = int(data.get("statusCode") or 0)
    except (TypeError, ValueError) as e:
        # 与旧实现一致：响应结构异常一律视为「无登录信息」，不让异常上抛打断登录
        logger.debug(f"[IPC] 登录信息管道返回非法 statusCode: {e}")
        return None

    return CurrentLoginInfo(
        status_code=status_code,
        user_id=str(data.get("userId") or ""),
        token=str(data.get("token") or ""),
        user_name=str(data.get("userName") or ""),
        nick_name=str(data.get("nickName") or ""),
        phone=str(data.get("phone") or ""),
        message=str(data.get("message") or ""),
        raw=data,
    )
