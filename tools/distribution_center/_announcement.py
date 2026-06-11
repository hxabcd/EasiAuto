import json
import traceback
import uuid
from datetime import datetime
from typing import Any

from PySide6.QtCore import QDate, Qt, QThread, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QScrollArea,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CalendarPicker,
    ComboBox,
    FluentIcon,
    InfoBar,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    TableWidget,
    TimePicker,
    VerticalSeparator,
)

from ._shared import (
    ANNOUNCEMENT_FILE_PATH,
    ANNOUNCEMENT_REPO,
    VALID_SEVERITIES,
    fetch_json_from_repo,
    put_json_to_repo,
    resolve_token,
)

FETCH = "FETCH"
PUSH = "PUSH"

TIMEZONE = "+08:00"


# ── Pure business logic ────────────────────────────────────────────────


def _parse_iso(value: str | None) -> tuple[QDate | None, QTime | None]:
    """Parse ISO datetime string to QDate/QTime pair."""
    if not value:
        return None, None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return QDate(dt.year, dt.month, dt.day), QTime(dt.hour, dt.minute)
    except (ValueError, TypeError):
        return None, None


def _format_iso(qd: QDate | None, qt: QTime | None) -> str | None:
    if qd is None or qt is None or not qd.isValid() or not qt.isValid():
        return None
    d = qd.toPython()
    t = qt.toPython()
    return f"{d.isoformat()}T{t.isoformat(timespec='seconds')}{TIMEZONE}"


def _today_qdt() -> tuple[QDate, QTime]:
    now = datetime.now()
    return QDate(now.year, now.month, now.day), QTime(now.hour, now.minute)


def normalize_announcement(item: dict[str, Any]) -> dict[str, Any]:
    raw_id = item.get("id", "")
    raw_title = item.get("title", "")
    raw_content = item.get("content", "")
    raw_published_at = item.get("published_at", "")

    if not isinstance(raw_id, str) or not raw_id.strip():
        raise ValueError("字段 id 不能为空")
    if not isinstance(raw_title, str) or not raw_title.strip():
        raise ValueError("字段 title 不能为空")
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise ValueError("字段 content 不能为空")

    severity = item.get("severity", "info")
    if severity not in VALID_SEVERITIES:
        severity = "info"

    start_at = (
        _format_iso(item.get("start_at_date"), item.get("start_at_time")) if item.get("start_at_enabled") else None
    )
    end_at = _format_iso(item.get("end_at_date"), item.get("end_at_time")) if item.get("end_at_enabled") else None

    if start_at and end_at:
        if datetime.fromisoformat(end_at) < datetime.fromisoformat(start_at):
            raise ValueError("结束时间不能早于开始时间")

    published_at = item.get("published_at", "")
    try:
        published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00")).isoformat()
    except (ValueError, TypeError):
        published_at = datetime.now().isoformat()

    link = item.get("link")
    if link is not None and not isinstance(link, str):
        raise ValueError("字段 link 必须是字符串")

    return {
        "id": raw_id.strip(),
        "title": raw_title.strip(),
        "content": raw_content.strip(),
        "severity": severity,
        "start_at": start_at,
        "end_at": end_at,
        "published_at": published_at,
        "link": link.strip() if isinstance(link, str) else "",
    }


def normalize_payload(payload: Any) -> dict[str, list[dict[str, Any]]]:
    if isinstance(payload, dict):
        raw = payload.get("announcements", [])
    elif isinstance(payload, list):
        raw = payload
    else:
        raise ValueError("公告文件格式不正确")

    if not isinstance(raw, list):
        raise ValueError("announcements 必须是数组")

    announcements = [normalize_announcement(item) for item in raw]
    ids = [item["id"] for item in announcements]
    if len(ids) != len(set(ids)):
        raise ValueError("存在重复的公告 id")

    announcements.sort(
        key=lambda item: datetime.fromisoformat(item["published_at"].replace("Z", "+00:00")),
        reverse=True,
    )
    return {"announcements": announcements}


# ── Network Thread ─────────────────────────────────────────────────────


class AnnouncementThread(QThread):
    finished_signal = Signal(str)
    data_signal = Signal(list, str)

    def __init__(self, action: str, token: str, payload: dict | None = None, sha: str | None = None):
        super().__init__()
        self.action = action
        self.token = token
        self.payload = payload
        self.sha = sha

    def run(self):
        try:
            if self.action == FETCH:
                raw_data, sha = fetch_json_from_repo(ANNOUNCEMENT_REPO, ANNOUNCEMENT_FILE_PATH, self.token)
                normalized = normalize_payload(raw_data)
                self.data_signal.emit(normalized["announcements"], sha)
                self.finished_signal.emit("ok")
            elif self.action == PUSH:
                if self.payload is None:
                    raise ValueError("缺少要发布的公告数据")
                put_json_to_repo(
                    ANNOUNCEMENT_REPO,
                    ANNOUNCEMENT_FILE_PATH,
                    self.sha,
                    self.payload,
                    f"Update announcements ({len(self.payload['announcements'])} items)",
                    self.token,
                )
                self.finished_signal.emit("ok")
        except Exception as e:
            traceback.print_exc()
            self.finished_signal.emit(str(e))


# ── Announcement Manager UI ────────────────────────────────────────────


class AnnouncementManagerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnnouncementManagerWidget")
        self.announcements: list[dict[str, Any]] = []
        self.remote_sha: str | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        header = QWidget(self)
        hl = QVBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 8)
        hl.addWidget(SubtitleLabel("公告管理器", header))

        action_row = QHBoxLayout()
        self.pull_btn = PrimaryPushButton("拉取远端", header)
        self.pull_btn.setIcon(FluentIcon.DOWNLOAD)
        self.pull_btn.clicked.connect(self._pull_remote)

        self.new_btn = PushButton("新建", header)
        self.new_btn.setIcon(FluentIcon.ADD)
        self.new_btn.clicked.connect(self._clear_form)

        self.delete_btn = PushButton("删除", header)
        self.delete_btn.setIcon(FluentIcon.DELETE)
        self.delete_btn.clicked.connect(self._delete_selected)

        self.publish_btn = PrimaryPushButton("发布到远端", header)
        self.publish_btn.setIcon(FluentIcon.SEND)
        self.publish_btn.clicked.connect(self._publish_remote)

        action_row.addWidget(self.pull_btn)
        action_row.addWidget(self.new_btn)
        action_row.addWidget(self.delete_btn)
        action_row.addWidget(self.publish_btn)
        action_row.addStretch(1)
        hl.addLayout(action_row)

        root.addWidget(header)

        # ── Horizontal split: table + separator + form ──
        h_split = QHBoxLayout()
        h_split.setContentsMargins(0, 0, 0, 0)
        h_split.setSpacing(0)

        # Left: table (title + published_at)
        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 4, 8)

        self.table = TableWidget(left_panel)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["标题", "发布时间"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._load_selected_to_form)
        left_layout.addWidget(self.table)

        h_split.addWidget(left_panel, 2)

        # Separator
        h_split.addWidget(VerticalSeparator(self))

        # Right: form with scroll
        right_panel = QScrollArea(self)
        right_panel.setWidgetResizable(True)
        right_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_panel.setStyleSheet("QScrollArea { background: transparent; }")

        form_container = QWidget(right_panel)
        self._build_form(form_container)
        right_panel.setWidget(form_container)

        h_split.addWidget(right_panel, 3)

        root.addLayout(h_split, 1)

        # ── Preview JSON footer ──
        self._preview_visible = False
        self.preview_toggle = QPushButton("📋 预览 JSON", self)
        self.preview_toggle.setStyleSheet("text-align: left; padding: 8px 24px; border: none; background: transparent;")
        self.preview_toggle.clicked.connect(self._toggle_preview)
        root.addWidget(self.preview_toggle)

        self.preview_edit = PlainTextEdit(self)
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setPlaceholderText("")
        self.preview_edit.setFixedHeight(160)
        self.preview_edit.hide()
        root.addWidget(self.preview_edit)

        self.announcements = []
        self._refresh_table()

    def _build_form(self, container: QWidget) -> None:
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel("编辑公告", container))

        # ── Title ──
        layout.addWidget(StrongBodyLabel("标题", container))
        self.title_edit = LineEdit(container)
        self.title_edit.setPlaceholderText("公告标题")
        layout.addWidget(self.title_edit)

        # ── Content ──
        layout.addWidget(StrongBodyLabel("正文", container))
        self.content_edit = PlainTextEdit(container)
        self.content_edit.setPlaceholderText("公告正文")
        self.content_edit.setFixedHeight(70)
        layout.addWidget(self.content_edit)

        # ── Severity ──
        layout.addWidget(StrongBodyLabel("级别", container))
        self.severity_combo = ComboBox(container)
        for item in VALID_SEVERITIES:
            self.severity_combo.addItem(item)
        layout.addWidget(self.severity_combo)

        # ── Link ──
        layout.addWidget(StrongBodyLabel("链接", container))
        self.link_edit = LineEdit(container)
        self.link_edit.setPlaceholderText("可选，详情链接")
        layout.addWidget(self.link_edit)

        # ── Start time ──
        layout.addWidget(StrongBodyLabel("开始时间", container))
        self.start_enabled_cb = QCheckBox("启用", container)
        self.start_picker = CalendarPicker(container)
        self.start_time_picker = TimePicker(container)
        default_d, default_t = _today_qdt()
        self.start_picker.setDate(default_d)
        self.start_time_picker.setTime(default_t)
        self.start_picker.setEnabled(False)
        self.start_time_picker.setEnabled(False)
        self.start_enabled_cb.toggled.connect(self.start_picker.setEnabled)
        self.start_enabled_cb.toggled.connect(self.start_time_picker.setEnabled)

        start_row = QHBoxLayout()
        start_row.setSpacing(8)
        start_row.addWidget(self.start_enabled_cb)
        start_row.addWidget(self.start_picker)
        start_row.addWidget(self.start_time_picker)
        start_row.addStretch(1)
        layout.addLayout(start_row)

        # ── End time ──
        layout.addWidget(StrongBodyLabel("结束时间", container))
        self.end_enabled_cb = QCheckBox("启用", container)
        self.end_picker = CalendarPicker(container)
        self.end_time_picker = TimePicker(container)
        self.end_picker.setDate(default_d)
        self.end_time_picker.setTime(default_t)
        self.end_picker.setEnabled(False)
        self.end_time_picker.setEnabled(False)
        self.end_enabled_cb.toggled.connect(self.end_picker.setEnabled)
        self.end_enabled_cb.toggled.connect(self.end_time_picker.setEnabled)

        end_row = QHBoxLayout()
        end_row.setSpacing(8)
        end_row.addWidget(self.end_enabled_cb)
        end_row.addWidget(self.end_picker)
        end_row.addWidget(self.end_time_picker)
        end_row.addStretch(1)
        layout.addLayout(end_row)

        layout.addStretch(1)

        self.save_btn = PrimaryPushButton("保存", container)
        self.save_btn.setIcon(FluentIcon.SAVE)
        self.save_btn.clicked.connect(self._save_current)
        layout.addWidget(self.save_btn)

    # ── Pull / Push ──

    def pull_if_token_available(self):
        token = resolve_token()
        if token:
            self._set_busy(True)
            self.thread = AnnouncementThread(FETCH, token)
            self.thread.data_signal.connect(self._on_fetch_data)
            self.thread.finished_signal.connect(lambda r: self._on_net_done("拉取", r))
            self.thread.start()

    def _pull_remote(self):
        token = resolve_token()
        if not token:
            InfoBar.error("错误", "请先在配置页设置 Token", parent=self)
            return

        self._set_busy(True)
        self.thread = AnnouncementThread(FETCH, token)
        self.thread.data_signal.connect(self._on_fetch_data)
        self.thread.finished_signal.connect(lambda r: self._on_net_done("拉取", r))
        self.thread.start()

    def _on_fetch_data(self, announcements: list, sha: str):
        self.announcements = announcements
        self.remote_sha = sha
        self._refresh_table()

    def _publish_remote(self):
        token = resolve_token()
        if not token:
            InfoBar.error("错误", "请先在配置页设置 Token", parent=self)
            return

        try:
            payload = normalize_payload({"announcements": self.announcements})
        except ValueError as e:
            InfoBar.error("错误", str(e), parent=self)
            return

        self._set_busy(True)
        self.thread = AnnouncementThread(PUSH, token, payload=payload, sha=self.remote_sha)
        self.thread.finished_signal.connect(lambda r: self._on_push_done(r))
        self.thread.start()

    def _on_push_done(self, result: str):
        self._on_net_done("发布", result)
        if result == "ok":
            self._pull_remote()

    def _on_net_done(self, action: str, result: str):
        self._set_busy(False)
        if result == "ok":
            InfoBar.success("成功", f"远端公告已{action}", parent=self)
        else:
            InfoBar.error(f"{action}失败", result, parent=self, duration=5000)

    def _set_busy(self, busy: bool):
        self.pull_btn.setEnabled(not busy)
        self.publish_btn.setEnabled(not busy)

    # ── Table ──

    def _refresh_table(self):
        self.table.setRowCount(len(self.announcements))
        for row, item in enumerate(self.announcements):
            self.table.setItem(row, 0, QTableWidgetItem(item["title"]))
            self.table.setItem(row, 1, QTableWidgetItem(item["published_at"]))

    def _load_selected_to_form(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.announcements):
            return

        item = self.announcements[row]
        self.title_edit.setText(item["title"])
        self.content_edit.setPlainText(item["content"])
        self.severity_combo.setCurrentText(item["severity"])
        self.link_edit.setText(item["link"] or "")

        # Start time
        start_d, start_t = _parse_iso(item.get("start_at"))
        if start_d is not None and start_t is not None and start_d.isValid() and start_t.isValid():
            self.start_picker.setDate(start_d)
            self.start_time_picker.setTime(start_t)
            self.start_enabled_cb.setChecked(True)
        else:
            self.start_enabled_cb.setChecked(False)
            default_d, default_t = _today_qdt()
            self.start_picker.setDate(default_d)
            self.start_time_picker.setTime(default_t)

        # End time
        end_d, end_t = _parse_iso(item.get("end_at"))
        if end_d is not None and end_t is not None and end_d.isValid() and end_t.isValid():
            self.end_picker.setDate(end_d)
            self.end_time_picker.setTime(end_t)
            self.end_enabled_cb.setChecked(True)
        else:
            self.end_enabled_cb.setChecked(False)
            default_d, default_t = _today_qdt()
            self.end_picker.setDate(default_d)
            self.end_time_picker.setTime(default_t)

    def _collect_form_data(self, existing_id: str = "") -> dict[str, Any]:
        return normalize_announcement(
            {
                "id": existing_id or str(uuid.uuid4()),
                "title": self.title_edit.text(),
                "content": self.content_edit.toPlainText(),
                "severity": self.severity_combo.currentText(),
                "published_at": datetime.now().isoformat(),
                "link": self.link_edit.text(),
                "start_at_date": self.start_picker.getDate() if self.start_enabled_cb.isChecked() else None,
                "start_at_time": self.start_time_picker.getTime() if self.start_enabled_cb.isChecked() else None,
                "start_at_enabled": self.start_enabled_cb.isChecked(),
                "end_at_date": self.end_picker.getDate() if self.end_enabled_cb.isChecked() else None,
                "end_at_time": self.end_time_picker.getTime() if self.end_enabled_cb.isChecked() else None,
                "end_at_enabled": self.end_enabled_cb.isChecked(),
            }
        )

    def _save_current(self):
        row = self.table.currentRow()
        existing_id = self.announcements[row]["id"] if 0 <= row < len(self.announcements) else ""

        try:
            announcement = self._collect_form_data(existing_id=existing_id)

            existing_idx = next(
                (i for i, item in enumerate(self.announcements) if item["id"] == announcement["id"]),
                None,
            )

            if 0 <= row < len(self.announcements):
                self.announcements[row] = announcement
            elif existing_idx is not None:
                self.announcements[existing_idx] = announcement
            else:
                self.announcements.append(announcement)

            self.announcements = normalize_payload({"announcements": self.announcements})["announcements"]
            self._refresh_table()
            InfoBar.success("成功", "公告已保存", parent=self)
        except Exception as e:
            InfoBar.error("保存失败", str(e), parent=self, duration=5000)

    def _delete_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.announcements):
            InfoBar.warning("提示", "请先选择一条公告", parent=self)
            return

        del self.announcements[row]
        self._refresh_table()
        self._clear_form()

    def _clear_form(self):
        self.table.clearSelection()
        self.title_edit.clear()
        self.content_edit.clear()
        self.severity_combo.setCurrentText("info")
        self.link_edit.clear()
        self.start_enabled_cb.setChecked(False)
        self.end_enabled_cb.setChecked(False)

    def _toggle_preview(self):
        self._preview_visible = not self._preview_visible
        self.preview_edit.setVisible(self._preview_visible)
        self.preview_toggle.setText("📋 隐藏 JSON" if self._preview_visible else "📋 预览 JSON")
        if self._preview_visible:
            try:
                payload = normalize_payload({"announcements": self.announcements})
                self.preview_edit.setPlainText(json.dumps(payload, indent=4, ensure_ascii=False))
            except Exception:
                pass
