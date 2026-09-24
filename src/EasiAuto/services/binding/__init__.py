"""档案与外部软件的科目绑定同步

- ``base``：与具体外部软件无关的契约（``SubjectRef``、``BindingSyncBackendBase``）
- ``classisland``：ClassIsland 后端实现

新增平台支持时，在 ``base`` 之上实现新的后端模块（每个后端一个模块），调用方按需选择后端。
"""

from .base import BindingSyncBackendBase, SubjectRef
from .classisland import ClassIslandBindingBackend

__all__ = [
    "BindingSyncBackendBase",
    "ClassIslandBindingBackend",
    "SubjectRef",
]
