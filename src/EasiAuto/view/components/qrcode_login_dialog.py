from __future__ import annotations

import time

import requests
from loguru import logger

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel
from qfluentwidgets import (
    BodyLabel,
    Dialog,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
)

QRCODE_URL = "https://id.seewo.com/scan/qrcode"
CHECK_URL = "https://id.seewo.com/scan/pcCheckQrcode"
QRCODE_TTL = 110
QR_SIZE = 260


class _PollWorker(QThread):
    qr_fetched = Signal(bytes, str)
    qr_fetch_failed = Signal(str)
    poll_status = Signal(int, dict)
    poll_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: requests.Session | None = None
        self._qrkey: str | None = None
        self._running: bool = False

    def setup_session(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://id.seewo.com/login",
            "X-Requested-With": "XMLHttpRequest",
        })

    def fetch_qr(self) -> None:
        self._running = True
        self.start()

    def stop(self) -> None:
        self._running = False
        if self._session:
            self._session.close()
            self._session = None

    def run(self) -> None:
        if not self._session:
            return
        try:
            url = f"{QRCODE_URL}?oriSys=EasiNote5&t=1484722930223.3638"
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            self._qrkey = self._session.cookies.get("qrkey", "")
            self.qr_fetched.emit(resp.content, self._qrkey)
        except Exception as e:
            self.qr_fetch_failed.emit(str(e))
            return

        if not self._running or not self._qrkey:
            return

        while self._running and self._qrkey:
            try:
                ts = int(time.time() * 1000)
                resp = self._session.get(
                    CHECK_URL,
                    params={"type": "long", "qrKey": self._qrkey, "_": ts},
                    timeout=25,
                )
                resp.raise_for_status()
                data = resp.json()
                inner = data.get("data", {})
                sc = inner.get("statusCode")
                self.poll_status.emit(sc, inner)

                if sc in (202, 300, 400):
                    break

            except requests.Timeout:
                continue
            except Exception as e:
                if self._running:
                    self.poll_error.emit(str(e))
                    self.msleep(2000)
                continue


class QRCodeLoginDialog(Dialog):

    def __init__(self, parent=None):
        super().__init__("二维码登录", "")
        self.setMinimumSize(420, 540)

        self._login_data: dict | None = None
        self._countdown: int = 0
        self._countdown_timer: QTimer | None = None
        self._worker: _PollWorker | None = None

        self.titleLabel.setText("请使用希沃白板或微信扫描二维码")
        self.contentLabel.hide()
        self.yesButton.hide()
        self.cancelButton.hide()

        self._init_ui()
        QTimer.singleShot(100, self._start_login)

    def _init_ui(self) -> None:
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setMinimumSize(QR_SIZE + 24, QR_SIZE + 24)
        self._qr_label.setStyleSheet("border: 2px solid #d0d0d0; border-radius: 10px; padding: 10px; background: white;")
        self.textLayout.addWidget(self._qr_label, 1)

        self._countdown_bar = ProgressBar()
        self._countdown_bar.setRange(0, QRCODE_TTL)
        self._countdown_bar.setValue(QRCODE_TTL)
        self._countdown_bar.setTextVisible(True)
        self._countdown_bar.setFormat("二维码有效时间剩余: %v 秒")
        self._countdown_bar.setFixedHeight(6)
        self.textLayout.addWidget(self._countdown_bar)

        self._status_label = BodyLabel("正在获取二维码...")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setWordWrap(True)
        self.textLayout.addWidget(self._status_label)

        self._refresh_btn = PrimaryPushButton("刷新二维码")
        self._refresh_btn.clicked.connect(self._start_login)
        self.buttonLayout.insertWidget(0, self._refresh_btn)

        self._cancel_btn = PushButton("取消")
        self._cancel_btn.clicked.connect(self.reject)
        self.buttonLayout.addWidget(self._cancel_btn)

    @property
    def login_data(self) -> dict | None:
        return self._login_data

    def _start_login(self) -> None:
        self._qr_label.clear()
        self._qr_label.setText("加载中...")
        self._status_label.setText("获取二维码中...")
        self._refresh_btn.setEnabled(False)

        if self._worker is not None:
            try:
                self._worker.qr_fetched.disconnect()
                self._worker.qr_fetch_failed.disconnect()
                self._worker.poll_status.disconnect()
                self._worker.poll_error.disconnect()
            except Exception:
                pass
            self._worker.stop()
            self._worker.terminate()
            self._worker.wait(100)

        self._worker = _PollWorker(self)
        self._worker.qr_fetched.connect(self._on_qr_fetched)
        self._worker.qr_fetch_failed.connect(self._on_qr_fetch_failed)
        self._worker.poll_status.connect(self._on_poll_status)
        self._worker.poll_error.connect(self._on_poll_error)
        self._worker.setup_session()
        self._worker.fetch_qr()

    def _on_qr_fetched(self, png_bytes: bytes, qrkey: str) -> None:
        if not qrkey:
            self._status_label.setText("获取二维码失败")
            self._refresh_btn.setEnabled(True)
            return

        pixmap = QPixmap()
        pixmap.loadFromData(png_bytes)
        if pixmap.isNull():
            self._status_label.setText("二维码解析失败")
            self._refresh_btn.setEnabled(True)
            return

        pixmap = pixmap.scaled(QR_SIZE, QR_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._qr_label.setPixmap(pixmap)

        self._countdown = QRCODE_TTL
        self._countdown_bar.setValue(QRCODE_TTL)
        self._status_label.setText("等待扫码...")
        self._refresh_btn.setEnabled(True)
        self._start_countdown()

    def _on_qr_fetch_failed(self, error: str) -> None:
        logger.error(f"二维码获取失败: {error}")
        self._status_label.setText(f"网络错误: {error}")
        self._refresh_btn.setEnabled(True)

    def _on_poll_status(self, sc: int, inner: dict) -> None:
        if sc == 200:
            pass
        elif sc == 201:
            self._status_label.setText("已扫描，请在手机上确认登录")
        elif sc == 202:
            self._worker.stop()
            self._stop_countdown()
            self._status_label.setText("登录成功")
            self._refresh_btn.setEnabled(False)
            self._cancel_btn.setEnabled(False)
            self._countdown_bar.setValue(QRCODE_TTL)
            self._countdown_bar.setFormat("登录成功")

            self._login_data = {
                "token": inner.get("token", ""),
                "userId": inner.get("userId", ""),
                "nickName": inner.get("nickName", ""),
                "phone": inner.get("phone", ""),
            }
            QTimer.singleShot(600, self.accept)

        elif sc in (300, 400):
            self._worker.stop()
            self._stop_countdown()
            self._status_label.setText(f"登录取消: {inner.get('message', '')}")
            self._refresh_btn.setEnabled(True)

    def _on_poll_error(self, error: str) -> None:
        logger.debug(f"轮询错误: {error}")

    def _start_countdown(self) -> None:
        self._stop_countdown()
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)
        self._countdown_timer.start(1000)

    def _stop_countdown(self) -> None:
        if self._countdown_timer:
            self._countdown_timer.stop()
            self._countdown_timer = None

    def _on_countdown_tick(self) -> None:
        self._countdown -= 1
        self._countdown_bar.setValue(max(self._countdown, 0))
        if self._countdown <= 0:
            self._stop_countdown()
            self._status_label.setText("二维码已过期，正在刷新...")
            self._start_login()

    def reject(self) -> None:
        self._cleanup_worker()
        super().reject()

    def closeEvent(self, event):
        self._cleanup_worker()
        super().closeEvent(event)

    def _cleanup_worker(self) -> None:
        self._stop_countdown()
        if self._worker is None:
            return
        self._worker.stop()
        self._worker.terminate()
        self._worker.wait(100)
