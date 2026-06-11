from __future__ import annotations

from typing import TYPE_CHECKING

from EasiAuto.models.config import LoginMethod

if TYPE_CHECKING:
    from .base import BaseAutomator

_registry: dict[LoginMethod, type[BaseAutomator]] = {}


def register(method: LoginMethod):
    """装饰器：将自动登录策略类注册到全局注册表"""

    def decorator(cls: type[BaseAutomator]) -> type[BaseAutomator]:
        _registry[method] = cls
        return cls

    return decorator


def get_automator_class(method: LoginMethod) -> type[BaseAutomator] | None:
    """根据登录方式获取对应的策略类"""
    return _registry.get(method)
