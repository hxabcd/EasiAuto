"""EasiAuto 自动化登录引擎

- ``manager``：登录任务的唯一入口（``automation_manager`` 单例 + 信号转发）
- ``automator``：四种登录策略（FIXED/CV/UIA/TOKEN）与基类、状态定义

调用方按 ``automation_manager`` 使用即可，无需关心内部分层。
"""

from .manager import AutomationManager, automation_manager

__all__ = [
    "AutomationManager",
    "automation_manager",
]
