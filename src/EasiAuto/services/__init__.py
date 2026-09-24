"""业务服务层：应用能力的实现与编排

- 有生命周期的单例服务（模块级单例 + 后台线程 + ``shutdown()``）：``announcement_service``、``update_service``
- 按后端扩展的能力：``binding``（档案与外部软件的科目绑定，契约与各后端分模块）

无业务概念的基础设施请放 ``core/``；外部系统的裸适配请放 ``integrations/``。
"""

from .announcement_service import announcement_service
from .update_service import update_service

__all__ = [
    "announcement_service",
    "update_service",
]
