"""单实例协调与实例间 IPC

- 通过命名互斥锁保证同一时间仅运行一个主实例
- 通过 QLocalServer/QLocalSocket 实现次实例向主实例传递命令行参数
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence

from loguru import logger
from shiboken6 import isValid

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def send_argv_to_primary(server_name: str, argv: Sequence[str], timeout_ms: int = 1200) -> bool:
    """次实例向主实例发送 argv"""
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if not socket.waitForConnected(timeout_ms):
        return False

    payload = json.dumps({"argv": list(argv)}, ensure_ascii=False).encode("utf-8")
    socket.write(payload)
    socket.flush()

    ok = socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    socket.close()
    return bool(ok)


def acquire_single_instance_mutex(name: str) -> int | None:
    """尝试获取单实例互斥锁

    Returns:
        int | None: 互斥锁句柄（需由调用方持有至进程结束）；已有实例在运行或创建失败时返回 None
    """
    import win32api
    import win32event
    import winerror

    try:
        mutex = win32event.CreateMutex(None, False, name)  # type: ignore[arg-type]
    except Exception as e:
        logger.error(f"创建互斥锁失败: {e}")
        return None

    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        logger.warning("检测到另一个正在运行的 EasiAuto 实例")
        return None

    return mutex


class ArgvIpcServer(QObject):
    """主实例本地 IPC 服务：接收次实例传入的 argv"""

    def __init__(self, server_name: str, on_argv: Callable[[list[str]], None]):
        super().__init__()
        self.server_name = server_name
        self.on_argv = on_argv
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._sockets: set[QLocalSocket] = set()

    def start(self) -> bool:
        QLocalServer.removeServer(self.server_name)
        if not self._server.listen(self.server_name):
            logger.error("启动 IPC 服务失败")
            return False
        logger.debug("IPC 服务已启动")
        return True

    def stop(self) -> None:
        self._server.close()
        for socket in list(self._sockets):
            socket.close()
            socket.deleteLater()
        self._sockets.clear()

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            self._sockets.add(socket)
            socket.readyRead.connect(lambda s=socket: self._on_socket_ready_read(s))
            socket.disconnected.connect(lambda s=socket: self._on_socket_disconnected(s))

    def _on_socket_ready_read(self, socket: QLocalSocket) -> None:
        # NOTE: 使用 lambda 捕获后 socket 可能已被 deleteLater（disconnected 触发顺序不定），
        # 此时直接访问 C++ 对象会抛出 RuntimeError
        if not isValid(socket):
            return
        try:
            raw = bytes(socket.readAll())
            if not raw:
                return
            payload = json.loads(raw.decode("utf-8"))
            argv = payload.get("argv")
            if isinstance(argv, list) and all(isinstance(x, str) for x in argv):
                logger.info("收到次实例参数转发")
                self.on_argv(argv)
            else:
                logger.warning("收到无效 IPC 数据: 缺少 argv")
        except Exception as e:
            logger.error(f"处理 IPC 消息失败: {e}")
        finally:
            if isValid(socket):
                socket.disconnectFromServer()

    def _on_socket_disconnected(self, socket: QLocalSocket) -> None:
        if socket in self._sockets:
            self._sockets.remove(socket)
        if isValid(socket):
            socket.deleteLater()
