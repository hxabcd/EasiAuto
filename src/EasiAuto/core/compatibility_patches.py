"""第三方库兼容性补丁。

集中放置针对依赖库已知问题的运行时补丁，应在 QApplication 创建后、窗口显示前应用。
"""

from __future__ import annotations

import pywintypes
from loguru import logger


def patch_frameless_window_uaci() -> None:
    """修补 qframelesswindow 在 UIPI 场景下的 GetCursorPos 崩溃。

    背景：当本进程（普通权限，中完整性）与提权子进程（管理员，高完整性）共存时，
    若高完整性窗口（如 UAC 同意窗口）处于前台，本进程在 nativeEvent 中调用
    win32api.GetCursorPos() 会因用户界面特权隔离（UIPI）返回 ERROR_ACCESS_DENIED，
    抛出未捕获的 pywintypes.error 导致崩溃。

    补丁包裹 WindowsFramelessWindowBase.nativeEvent，捕获该错误并降级为默认处理，
    仅影响命中测试的边缘场景，正常情况无副作用。
    """
    try:
        from qframelesswindow.windows import WindowsFramelessWindowBase
    except Exception as e:
        logger.debug(f"qframelesswindow 不可用，跳过 UIPI 补丁: {e}")
        return

    if getattr(WindowsFramelessWindowBase, "_uaci_patched", False):
        return

    original_native_event = WindowsFramelessWindowBase.nativeEvent

    def nativeEvent(self, eventType, message):  # type: ignore[no-untyped-def]
        try:
            return original_native_event(self, eventType, message)
        except pywintypes.error as e:
            # 仅吞 GetCursorPos 的拒绝访问（UIPI），其余重新抛出
            if getattr(e, "winerror", None) == 5 and getattr(e, "funcname", "") == "GetCursorPos":
                logger.debug(f"GetCursorPos 被 UIPI 拒绝，已降级处理: {e}")
                return False, 0
            raise

    WindowsFramelessWindowBase.nativeEvent = nativeEvent  # type: ignore[assignment]
    WindowsFramelessWindowBase._uaci_patched = True  # type: ignore[attr-defined]
    logger.debug("已应用 qframelesswindow UIPI 兼容补丁")


def apply_all() -> None:
    """应用全部兼容性补丁"""
    patch_frameless_window_uaci()
