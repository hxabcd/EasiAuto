from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

import requests
from loguru import logger

from PySide6.QtCore import QObject, QThread, Signal, Slot

ANNOUNCEMENT_URL = "https://easiauto.0xabcd.dev/announcements.json"
ANNOUNCEMENT_TIMEOUT = (3, 5)
ANNOUNCEMENT_HEADERS = {"User-Agent": "EasiAuto/announcement", "Cache-Control": "no-cache"}
AnnouncementSeverity = Literal["info", "warning", "error"]


class AnnouncementParseError(ValueError):
    pass


class AnnouncementFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Announcement:
    id: str
    title: str
    content: str
    severity: AnnouncementSeverity
    start_at: datetime | None
    end_at: datetime | None
    published_at: datetime
    link: str | None

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        if self.start_at and now < self.start_at:
            return False
        return not (self.end_at and now > self.end_at)


class AnnouncementWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, service: AnnouncementService) -> None:
        super().__init__()
        self._service = service

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.fetch()
            self.finished.emit(result)
        except Exception as e:
            logger.warning(f"拉取公告失败: {e}")
            self.failed.emit(str(e))


class AnnouncementService(QObject):
    fetch_started = Signal()
    fetch_finished = Signal(object)
    fetch_failed = Signal(str)

    def __init__(self, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.session = requests.Session()
        self._threads: list[QThread] = []
        self._thread_counter = 0
        self._shutting_down = False

    def fetch(self) -> list[Announcement]:
        response = self.session.get(ANNOUNCEMENT_URL, timeout=ANNOUNCEMENT_TIMEOUT, headers=ANNOUNCEMENT_HEADERS)
        try:
            response.raise_for_status()
        except requests.RequestException as e:
            raise AnnouncementFetchError(f"请求失败: {e}") from e

        try:
            payload = response.json()
        except ValueError as e:
            raise AnnouncementFetchError("公告数据不是有效的 JSON") from e

        return self._parse_payload(payload)

    def fetch_async(self) -> None:
        worker = AnnouncementWorker(self)

        def _connect_signals(thread: QThread) -> None:
            thread.started.connect(self.fetch_started)
            thread.started.connect(worker.run)
            worker.finished.connect(self.fetch_finished)
            worker.failed.connect(self.fetch_failed)
            worker.finished.connect(thread.quit)
            worker.failed.connect(thread.quit)

        self._start_worker_thread(worker, connect_signals=_connect_signals)

    def shutdown(self, *, wait_ms: int = 2) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            self.session.close()
            self._cleanup_threads()
            for thread in list(self._threads):
                if not thread.isRunning():
                    continue
                thread.quit()
                thread.wait(wait_ms)
        finally:
            self._cleanup_threads()
            self._shutting_down = False

    def _parse_payload(self, payload: Any) -> list[Announcement]:
        if isinstance(payload, dict):
            raw_items = payload.get("announcements", [])
        elif isinstance(payload, list):
            raw_items = payload
        else:
            raise AnnouncementFetchError("公告数据格式不正确")

        if not isinstance(raw_items, list):
            raise AnnouncementFetchError("公告列表格式不正确")

        now = datetime.now(UTC)
        announcements: list[Announcement] = []
        for item in raw_items:
            if not isinstance(item, dict):
                logger.warning("跳过非对象公告项")
                continue

            try:
                announcement = self._parse_announcement(item)
            except AnnouncementParseError as e:
                logger.warning(f"跳过无效公告项: {e}")
                continue

            if announcement.is_active(now):
                announcements.append(announcement)

        announcements.sort(key=lambda item: item.published_at, reverse=True)
        return announcements

    def _parse_announcement(self, item: dict[str, Any]) -> Announcement:
        raw_id = item.get("id")
        raw_title = item.get("title")
        raw_content = item.get("content")
        raw_published_at = item.get("published_at")

        if not all(
            isinstance(value, str) and value.strip() for value in [raw_id, raw_title, raw_content, raw_published_at]
        ):
            raise AnnouncementParseError("缺少必要字段")

        raw_severity = item.get("severity", "info")
        severity: AnnouncementSeverity = raw_severity if raw_severity in {"info", "warning", "error"} else "info"
        start_at = self._parse_datetime(item.get("start_at"), field_name="start_at")
        end_at = self._parse_datetime(item.get("end_at"), field_name="end_at")
        published_at = self._parse_datetime(raw_published_at, required=True, field_name="published_at")
        if end_at and start_at and end_at < start_at:
            raise AnnouncementParseError("结束时间早于开始时间")

        raw_link = item.get("link")
        link = raw_link.strip() if isinstance(raw_link, str) and raw_link.strip() else None

        return Announcement(
            id=cast(str, raw_id).strip(),
            title=cast(str, raw_title).strip(),
            content=cast(str, raw_content).strip(),
            severity=severity,
            start_at=start_at,
            end_at=end_at,
            published_at=cast(datetime, published_at),
            link=link,
        )

    def _parse_datetime(
        self,
        value: Any,
        *,
        required: bool = False,
        field_name: str,
    ) -> datetime | None:
        if value is None:
            if required:
                raise AnnouncementParseError(f"字段 {field_name} 缺失")
            return None

        if not isinstance(value, str) or not value.strip():
            raise AnnouncementParseError(f"字段 {field_name} 不是有效时间")

        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as e:
            raise AnnouncementParseError(f"字段 {field_name} 不是 ISO 时间") from e

        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

    def _cleanup_threads(self) -> None:
        self._threads = [thread for thread in self._threads if thread.isRunning()]

    def _start_worker_thread(self, worker: QObject, *, connect_signals) -> QThread:
        self._cleanup_threads()

        thread = QThread()
        self._thread_counter += 1
        thread.setObjectName(f"AnnouncementWorker:{worker.__class__.__name__}#{self._thread_counter}")
        worker.moveToThread(thread)
        thread._worker_ref = worker  # type: ignore

        connect_signals(thread)

        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._threads.append(thread)
        thread.start()
        return thread


announcement_service = AnnouncementService()
