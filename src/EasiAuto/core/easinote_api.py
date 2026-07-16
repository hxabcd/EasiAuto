"""希沃白板 (EasiNote) 登录 API — 基于 dnSpy 反编译 5.2.4.9440。"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

import requests

__all__ = [
    "SeewoClient",
    "SeewoLoginError",
    "SeewoAuthError",
    "SeewoNetworkError",
    "SeewoNeedCaptcha",
    "LoginResult",
    "UserInfo",
    "UserProfile",
    "login",
    "hash_password",
]

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://edu.seewo.com"
_DEFAULT_APP_CODE = "EasiNote5"
_DEFAULT_APP_BRAND = ""
_LOGIN_ENDPOINT = "/api/v1/auth/login"
_USER_INFO_ENDPOINT = "/api/v2/user/info"


def hash_password(plain_password: str) -> str:
    """MD5 哈希密码，对应 C# ``SecurityUtility.Encrypt32()``。"""
    return hashlib.md5(plain_password.encode("utf-8")).hexdigest()


# ─── 数据模型 ────────────────────────────────────────


@dataclass(slots=True)
class UserInfo:
    """登录响应中的 user 字段。"""

    uid: str
    username: str
    nick_name: str
    phone: str = ""
    email: str = ""
    photo_url: str = ""
    account_id: str = ""
    real_name: str = ""
    unit_id: str = ""
    account_type: int = 0
    gender: int = 0
    wechat_uid: str = ""
    dingding_uid: str = ""
    app_code: str = ""
    address: str = ""
    is_register: int = 0
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> UserInfo:
        user = data.get("user", data)
        return cls(
            uid=user.get("uid", ""),
            username=user.get("username", ""),
            nick_name=user.get("nickName", user.get("nickname", "")),
            phone=user.get("phone", ""),
            email=user.get("email", ""),
            photo_url=user.get("photoUrl", ""),
            account_id=user.get("accountId", ""),
            real_name=user.get("realName", ""),
            unit_id=user.get("unitId", ""),
            account_type=user.get("accountType", 0),
            gender=user.get("gender", 0),
            wechat_uid=user.get("wechatUid", ""),
            dingding_uid=user.get("dingdingUid", ""),
            app_code=user.get("appCode", ""),
            address=user.get("address", ""),
            is_register=data.get("isRegister", 0),
            _raw=data,
        )


@dataclass(slots=True)
class LoginResult:
    """登录成功时的完整结果。"""

    token: str
    user: UserInfo
    is_register: int = 0
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> LoginResult:
        inner = response.get("data", response)
        return cls(
            token=inner.get("token", ""),
            user=UserInfo.from_response(inner),
            is_register=inner.get("isRegister", 0),
            _raw=response,
        )


@dataclass(slots=True)
class UserProfile:
    """``GET /api/v2/user/info`` 返回的用户详情。"""

    photo_url: str = ""
    animated_photo: str = ""
    phone: str = ""
    email: str = ""
    nick_name: str = ""
    real_name: str = ""
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> UserProfile:
        user_data = data.get("data", data)
        extended = user_data.get("userInfoExtendVo") or {}
        return cls(
            photo_url=user_data.get("photoUrl", ""),
            animated_photo=extended.get("animatedUserPhoto", ""),
            phone=user_data.get("phone", ""),
            email=user_data.get("email", ""),
            nick_name=user_data.get("nickName", ""),
            real_name=user_data.get("realName", ""),
            _raw=data,
        )

    @property
    def avatar(self) -> str | None:
        """头像 URL，优先 animatedUserPhoto > photoUrl。"""
        return self.animated_photo or self.photo_url or None


# ─── 异常 ────────────────────────────────────────────


class SeewoLoginError(Exception):
    def __init__(self, message: str, code: int | None = None, response: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.response = response


class SeewoAuthError(SeewoLoginError):
    """密码错误 / 账号不存在。"""


class SeewoNetworkError(SeewoLoginError):
    """网络请求失败"""


class SeewoNeedCaptcha(SeewoLoginError):
    """需要图形验证码"""

    def __init__(self, message: str = "需要验证码", response: Any = None) -> None:
        super().__init__(message, code=4906, response=response)


# ─── 客户端 ──────────────────────────────────────────


class SeewoClient:
    """希沃账号服务客户端。每个实例维护独立 Session，建议按线程创建或使用上下文管理器。"""

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        app_code: str = _DEFAULT_APP_CODE,
        app_brand: str = _DEFAULT_APP_BRAND,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.app_code = app_code
        self.app_brand = app_brand
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "EasiNote/5.2.4",
                "Accept": "application/json",
            }
        )

    def __enter__(self) -> SeewoClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    # ---- 内部 ----

    def _build_cookie(self) -> str:
        cookie = f"x-auth-app={self.app_code}"
        if self.app_brand:
            cookie += f"; x-auth-brand={self.app_brand}"
        return cookie

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers["Cookie"] = self._build_cookie()
        kwargs.setdefault("timeout", self.timeout)
        return self._session.request(method, url, headers=headers, **kwargs)

    # ---- 登录 ----

    def login(
        self,
        username: str,
        password: str,
        *,
        captcha_key: str | None = None,
        captcha_content: str | None = None,
        phone_country_code: str | None = None,
    ) -> LoginResult:
        """账号+密码登录。密码自动 MD5 哈希"""
        body: dict[str, Any] = {
            "username": username,
            "password": hash_password(password),
        }
        if captcha_key and captcha_content:
            body["captcha"] = {"key": captcha_key, "captcha": captcha_content}
        if phone_country_code:
            body["phoneCountryCode"] = phone_country_code

        try:
            resp = self._request("POST", _LOGIN_ENDPOINT, json=body)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SeewoNetworkError(f"网络请求失败: {exc}") from exc

        response: dict[str, Any] = resp.json()
        if response.get("error_code") != 0:
            self._raise_for_error(response)
        return LoginResult.from_response(response)

    def login_with_hash(self, username: str, password_hash: str) -> LoginResult:
        """使用已 MD5 哈希的密码登录"""
        body = {"username": username, "password": password_hash}
        try:
            resp = self._request("POST", _LOGIN_ENDPOINT, json=body)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SeewoNetworkError(f"网络请求失败: {exc}") from exc

        response: dict[str, Any] = resp.json()
        if response.get("error_code") != 0:
            self._raise_for_error(response)
        return LoginResult.from_response(response)

    # ---- 用户信息 ----

    def get_user_info(self, token: str) -> UserProfile | None:
        """通过 token 获取用户详情（含头像），失败返回 None"""
        cookie = f"x-auth-app={self.app_code}; x-auth-token={token}"
        try:
            resp = self._request("GET", _USER_INFO_ENDPOINT, headers={"Cookie": cookie})
            if resp.status_code != 200:
                return None
            return UserProfile.from_response(resp.json())
        except requests.RequestException:
            return None

    def get_avatar(self, token: str) -> str | None:
        """通过 token 获取头像 URL"""
        profile = self.get_user_info(token)
        return profile.avatar if profile else None

    # ----

    @staticmethod
    def _raise_for_error(data: dict[str, Any]) -> None:
        code = data.get("error_code", -1)
        msg = data.get("message", "未知错误")
        if code == 4906:
            raise SeewoNeedCaptcha(msg, response=data)
        if code in (4908, 4909):
            raise SeewoAuthError(f"账号或密码错误 ({code})", code=code, response=data)
        raise SeewoLoginError(f"登录失败 [{code}]: {msg}", code=code, response=data)


# ─── 便捷函数 ────────────────────────────────────────


def login(
    username: str,
    password: str,
    *,
    captcha_key: str | None = None,
    captcha_content: str | None = None,
    phone_country_code: str | None = None,
    base_url: str = _DEFAULT_BASE_URL,
    app_code: str = _DEFAULT_APP_CODE,
) -> LoginResult:
    """一行登录，每次创建临时客户端。复用 session 请用 ``SeewoClient``"""
    with SeewoClient(base_url=base_url, app_code=app_code) as client:
        return client.login(
            username=username,
            password=password,
            captcha_key=captcha_key,
            captcha_content=captcha_content,
            phone_country_code=phone_country_code,
        )


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        username, password = sys.argv[1], sys.argv[2]
    else:
        username = input("手机号: ").strip()
        password = input("密码: ").strip()  # noqa: S590 (CLI 测试用途)

    try:
        result = login(username, password)
        print(f"""✅ 登录成功!
   Token:    {result.token}
   用户:     {result.user.nick_name}
   用户名:   {result.user.username}
   UID:      {result.user.uid}
   手机:     {result.user.phone}""")  # noqa: T201
    except SeewoNeedCaptcha:
        print("⚠️ 需要图形验证码")  # noqa: T201
    except SeewoAuthError as e:
        print(f"❌ 认证失败: {e}")  # noqa: T201
    except SeewoLoginError as e:
        print(f"❌ 登录失败 [{e.code}]: {e}")  # noqa: T201
