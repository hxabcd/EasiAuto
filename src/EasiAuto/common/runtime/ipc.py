from __future__ import annotations

import json
from collections.abc import Callable, Sequence

from loguru import logger

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket


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
        # 清理可能遗留的旧 server 名称
        QLocalServer.removeServer(self.server_name)
        if not self._server.listen(self.server_name):
            logger.error(f"启动 IPC 服务失败: {self.server_name}")
            return False
        logger.debug(f"IPC 服务已启动: {self.server_name}")
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
        try:
            raw = bytes(socket.readAll())
            if not raw:
                return
            payload = json.loads(raw.decode("utf-8"))
            argv = payload.get("argv")
            if isinstance(argv, list) and all(isinstance(x, str) for x in argv):
                logger.info(f"收到次实例参数转发: argv={argv!r}")
                self.on_argv(argv)
            else:
                logger.warning("收到无效 IPC 数据: 缺少 argv")
        except Exception as e:
            logger.error(f"处理 IPC 消息失败: {e}")
        finally:
            socket.disconnectFromServer()

    def _on_socket_disconnected(self, socket: QLocalSocket) -> None:
        if socket in self._sockets:
            self._sockets.remove(socket)
        socket.deleteLater()


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
