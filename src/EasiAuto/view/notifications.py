"""Windows 11 Toast 通知服务，支持 PySide6 信号回调

使用原生 WinRT API 构建 XML 并创建通知，确保 WinRT 事件回调
(add_activated / add_dismissed / add_failed) 在 show() 之前注册，
避免通知显示后回调还未就绪的问题。
每条通知返回一个 ToastHandle，调用方对其专属信号绑定回调。
"""

from collections.abc import Callable
from typing import Any

from windows11toast import IconCrop, IconPlacement
from windows11toast.constants import DEFAULT_APP_ID, DEFAULT_XML_TEMPLATE
from windows11toast.utils import activated_args
from windows11toast.xml_builder import add_button, add_icon, add_text, set_attribute
from winrt.windows.data.xml.dom import XmlDocument
from winrt.windows.foundation import EventRegistrationToken
from winrt.windows.ui.notifications import (
    ToastDismissedEventArgs,
    ToastFailedEventArgs,
    ToastNotification,
    ToastNotificationManager,
)

from PySide6.QtCore import QObject, Signal

from EasiAuto.core.resources import get_resource


class ToastHandle(QObject):
    """单条通知的事件句柄，事件触发后自动清理 WinRT 注册"""

    activated = Signal(dict)
    """通知被点击时发射，参数: {'arguments': str, 'user_input': dict}"""

    dismissed = Signal(object)
    """通知被关闭时发射（超时/手动关闭/清除），参数: ToastDismissalReason"""

    failed = Signal(object)
    """通知发送失败时发射，参数: error_code"""

    def __init__(
        self,
        notification: ToastNotification,
        tokens: list[EventRegistrationToken],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._notification = notification
        self._tokens = tokens
        self._cleanup_done = False

        # 任一事件触发即清理
        self.activated.connect(self._cleanup)
        self.dismissed.connect(self._cleanup)
        self.failed.connect(self._cleanup)
        self.destroyed.connect(self._remove_tokens)

    def _cleanup(self) -> None:
        if self._cleanup_done:
            return
        self._cleanup_done = True
        self._remove_tokens()
        self.deleteLater()

    def _remove_tokens(self) -> None:
        if self._notification is None:
            return
        try:
            self._notification.remove_activated(self._tokens[0])
            self._notification.remove_dismissed(self._tokens[1])
            self._notification.remove_failed(self._tokens[2])
        except OSError:
            pass


class ToastNotifier:
    """通知工厂，每次 show() 返回 ToastHandle

    使用示例：

        notifier = ToastNotifier(self) # parent 确保 handle 生命周期

        # 简单通知
        notifier.show("标题", "正文")

        # 绑定按钮回调
        handle = notifier.show(
            "更新可用",
            "新版本：2.0.0",
            buttons=[
                {"content": "立即更新", "arguments": "update", "activationType": "foreground"},
                {"content": "忽略", "arguments": "dismiss", "activationType": "foreground"},
            ],
        )
        handle.activated.connect(lambda args: print(args["arguments"]))
    """

    def __init__(self, parent: QObject | None = None):
        self._parent = parent

    def show(
        self,
        title: str | None = None,
        body: str | None = None,
        *,
        on_click: Callable | str | None = None,
        **kwargs: Any,
    ) -> ToastHandle:
        """显示通知，返回 ToastHandle 用于绑定回调"""
        buttons = kwargs.pop("buttons", None)
        app_id = kwargs.pop("app_id", DEFAULT_APP_ID)
        icon_src = kwargs.pop("icon_src", get_resource("icons/EasiAuto.ico"))

        # 1. 构建 XML
        document = XmlDocument()
        document.load_xml(DEFAULT_XML_TEMPLATE.format(scenario="default"))

        if isinstance(on_click, str):
            set_attribute(document, "/toast", "launch", on_click)

        if title:
            add_text(title, document)
        if body:
            add_text(body, document)

        if icon_src:
            add_icon(icon_src, IconPlacement.APP_LOGO_OVERRIDE, IconCrop.NONE, document)

        if buttons:
            for btn in buttons:
                if btn.get("activationType") == "protocol" and not btn.get("arguments", "").startswith("http"):
                    btn["arguments"] = "http:" + btn["arguments"]
                add_button(btn, document)

        # 2. 创建通知对象
        notification = ToastNotification(document)

        # 3. 注册 WinRT 回调（在 show() 之前）
        tokens: list[EventRegistrationToken] = []

        def _on_activated(sender: Any, event: Any) -> None:
            args = activated_args(sender, event)
            if args["arguments"].startswith("http:"):
                args["arguments"] = args["arguments"].removeprefix("http:")
            handle.activated.emit(args)

        def _on_dismissed(_sender: Any, event: Any) -> None:
            handle.dismissed.emit(ToastDismissedEventArgs._from(event).reason)  # pyright: ignore[reportAttributeAccessIssue]

        def _on_failed(_sender: Any, event: Any) -> None:
            handle.failed.emit(ToastFailedEventArgs._from(event).error_code)  # pyright: ignore[reportAttributeAccessIssue]

        handle = ToastHandle(notification, tokens, self._parent)

        tokens.append(notification.add_activated(_on_activated))
        tokens.append(notification.add_dismissed(_on_dismissed))
        tokens.append(notification.add_failed(_on_failed))

        if callable(on_click):
            handle.activated.connect(on_click)

        # 4. 显示通知
        try:
            notifier = ToastNotificationManager.create_toast_notifier()
        except Exception:
            notifier = ToastNotificationManager.create_toast_notifier_with_id(app_id)
        notifier.show(notification)

        return handle
