from __future__ import annotations

import json
from collections.abc import Sequence

from PySide6.QtNetwork import QLocalSocket


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
