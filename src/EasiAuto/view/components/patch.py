from __future__ import annotations

from pathlib import Path
from typing import cast

from loguru import logger

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, SwitchButton

from EasiAuto.models.config import config
from EasiAuto.view.components.setting_card import CardType as SettingCardType
from EasiAuto.view.components.setting_card import SettingCard


class PatchThread(QThread):
    """执行修补/撤销修补的工作线程。

    - 已具备管理员权限或开发环境（无打包 exe 可提权）时，直接调用修补函数；
    - 否则请求 UAC 提权，运行子进程 `patch --on/--off`。

    在工作线程中执行以避免阻塞 UI 线程（DllPatcher 可能耗时数十秒）。

    Attributes:
        enable: True 表示修补，False 表示撤销修补
        done: 完成信号，参数为 (ok, code, launched) —— ok 操作是否成功，code 子进程退出码，launched 子进程是否成功启动
    """

    done = Signal(bool, int, bool)

    def __init__(self, enable: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.enable = enable

    def run(self) -> None:
        from EasiAuto.automation.easinote_patcher import (
            PATCH_ERR_EASINOTE_NOT_FOUND,
            PATCH_ERR_UNKNOWN,
            PATCH_OK,
            patch_easinote,
            unpatch_easinote,
        )

        if self._run_directly():
            path = self._resolve_path()
            if path is None:
                self.done.emit(False, PATCH_ERR_EASINOTE_NOT_FOUND, True)
                return

            action = patch_easinote if self.enable else unpatch_easinote
            try:
                ok = action(path)
            except Exception as e:
                logger.error(f"{'修补' if self.enable else '撤销修补'}希沃白板时发生异常: {e}")
                self.done.emit(False, PATCH_ERR_UNKNOWN, True)
                return

            self.done.emit(ok, PATCH_OK if ok else PATCH_ERR_UNKNOWN, True)
            return

        from EasiAuto.core.elevation import run_elevated_wait

        launched, code = run_elevated_wait(f"patch {'--on' if self.enable else '--off'}")
        self.done.emit(launched and code == PATCH_OK, code, launched)

    @staticmethod
    def _run_directly() -> bool:
        from EasiAuto.consts import IS_DEV
        from EasiAuto.core.elevation import is_admin

        return is_admin() or IS_DEV

    @staticmethod
    def _resolve_path():
        from EasiAuto.automation.utils import resolve_easinote_path

        return resolve_easinote_path()[0]


def patch_error_message(code: int, launched: bool) -> str:
    """根据子进程退出码返回用户可读的错误信息"""
    from EasiAuto.automation.easinote_patcher import (
        PATCH_ERR_EASINOTE_NOT_FOUND,
        PATCH_ERR_OPERATION_FAILED,
        PATCH_ERR_UNKNOWN,
    )

    if not launched:
        return "未能取得管理员权限"
    if code == PATCH_ERR_EASINOTE_NOT_FOUND:
        return "未找到希沃白板安装路径"
    if code == PATCH_ERR_OPERATION_FAILED:
        return "文件可能被占用，请关闭希沃白板后重试"
    if code == PATCH_ERR_UNKNOWN:
        return "发生未知错误，请查看日志获取详细信息"
    # 其他非零退出码（如 0/1/2）：程序未能正常执行到 patch 逻辑
    return f"程序异常退出（退出码：{code}），请查看日志获取详细信息"


class PatcherSettingCard(SettingCard):
    """修补希沃白板"开关卡片，切换开关立即执行修补/撤销（配置页与首次设置向导共用）

    Attributes:
        switch: 开关控件
        path: 检测到的希沃白板路径，未找到为 None
        started: 修补开始信号
        finished: 修补完成信号，参数 ok 表示操作是否成功
    """

    started = Signal()
    finished = Signal(bool)

    def __init__(self, *, is_item: bool = False, item_margin: bool = True, parent: QWidget | None = None):
        super().__init__(
            card_type=SettingCardType.SWITCH,
            icon=FluentIcon.CODE,
            title="修补希沃白板",
            content="将登录相关的组件修补至希沃白板",
            is_item=is_item,
            item_margin=item_margin,
            parent=parent,
        )
        self.switch = cast(SwitchButton, self.widget)
        self.path: Path | None = None
        self._patch_thread: PatchThread | None = None

        from EasiAuto.automation.utils import resolve_easinote_path

        self.path, _ = resolve_easinote_path()
        if self.path is None:
            self.switch.setEnabled(False)
            self.contentLabel.setText(f"{self.contentLabel.text()}\n未找到希沃白板路径，暂不可用")
            return

        # 先同步状态再连接信号，避免初始化时触发修补
        from EasiAuto.automation.easinote_patcher import is_easinote_patched

        self.switch.setChecked(is_easinote_patched(self.path))
        self.switch.checkedChanged.connect(self._on_switch_changed)

    def _on_switch_changed(self, value: bool):
        """开关切换：立即执行修补/撤销"""
        self.switch.setEnabled(False)

        thread = PatchThread(value, parent=self)
        # 挂到自身持有引用，防止 Python 侧在回调前回收线程对象
        self._patch_thread = thread

        def on_done(ok: bool, code: int, launched: bool):
            content = patch_error_message(code, launched) if not ok else None
            self._finish_patch(value, ok, content=content)

        def on_finished():
            self._patch_thread = None
            thread.deleteLater()

        thread.done.connect(on_done)
        thread.started.connect(self.started)
        thread.finished.connect(on_finished)  # self.finished 在 _finish_patch 中发射
        thread.start()

    def _finish_patch(self, value: bool, ok: bool, content: str | None):
        """统一处理修补结果：更新配置、失败时回弹开关、恢复可用状态"""
        config.Internal.IsEasiNotePatched = value if ok else not value
        if not ok:
            InfoBar.error(
                title=f"{'修补' if value else '撤销修补'}失败",
                content=content or "文件可能被占用，请关闭希沃白板后重试",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window(),
            )
            self.switch.blockSignals(True)
            self.switch.setChecked(not value)
            self.switch.blockSignals(False)
        self.switch.setEnabled(True)
        self.finished.emit(ok)
