"""Qt 对象与抽象基类的兼容元类。"""

from __future__ import annotations

from abc import ABCMeta

from PySide6.QtCore import QObject


class QABCMeta(type(QObject), ABCMeta):  # type: ignore
    """QObject 与抽象基类的兼容元类"""
