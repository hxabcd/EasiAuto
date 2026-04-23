import argparse
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScroller,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    FluentTranslator,
    FluentWindow,
    InfoBar,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TableWidget,
    Theme,
    setTheme,
)

ANNOUNCEMENT_REPO = "hxabcd/EasiAutoWeb"
ANNOUNCEMENT_FILE_PATH = "public/announcements.json"
TEMPLATE_PATH = Path(__file__).parent / "data" / "announcements.template.json"
VALID_SEVERITIES = ("info", "warning", "error")
REQUEST_TIMEOUT = 15


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _resolve_default_branch(repo: str, token: str) -> str:
    resp = requests.get(f"https://api.github.com/repos/{repo}", headers=_github_headers(token), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("default_branch", "main")


def _normalize_datetime(value: Any, *, field_name: str, required: bool = False) -> str | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"字段 {field_name} 不能为空")
        return None

    if not isinstance(value, str):
        raise ValueError(f"字段 {field_name} 必须是字符串")

    text = value.strip()
    if not text:
        if required:
            raise ValueError(f"字段 {field_name} 不能为空")
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"字段 {field_name} 不是有效的 ISO 时间") from e

    return parsed.isoformat()


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

    start_at = _normalize_datetime(item.get("start_at"), field_name="start_at")
    end_at = _normalize_datetime(item.get("end_at"), field_name="end_at")
    published_at = _normalize_datetime(raw_published_at, field_name="published_at", required=True)

    if start_at and end_at:
        start_dt = datetime.fromisoformat(start_at)
        end_dt = datetime.fromisoformat(end_at)
        if end_dt < start_dt:
            raise ValueError("字段 end_at 不能早于 start_at")

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
        raw_announcements = payload.get("announcements", [])
    elif isinstance(payload, list):
        raw_announcements = payload
    else:
        raise ValueError("公告文件格式不正确")

    if not isinstance(raw_announcements, list):
        raise ValueError("announcements 必须是数组")

    announcements = [normalize_announcement(item) for item in raw_announcements]
    ids = [item["id"] for item in announcements]
    if len(ids) != len(set(ids)):
        raise ValueError("存在重复的公告 id")

    announcements.sort(
        key=lambda item: datetime.fromisoformat(item["published_at"].replace("Z", "+00:00")), reverse=True
    )
    return {"announcements": announcements}


def load_template_payload() -> dict[str, list[dict[str, Any]]]:
    if TEMPLATE_PATH.exists():
        return normalize_payload(json.loads(TEMPLATE_PATH.read_text(encoding="utf-8")))

    return {
        "announcements": [
            {
                "id": "2026-04-23-example-info",
                "title": "公告标题",
                "content": "这里填写公告正文。建议控制在 2 行以内，避免设置页展示过长。",
                "severity": "info",
                "start_at": "2026-04-23T00:00:00+08:00",
                "end_at": "2026-05-01T00:00:00+08:00",
                "published_at": "2026-04-23T12:00:00+08:00",
                "link": "https://easiauto.0xabcd.dev/",
            }
        ]
    }


def fetch_remote_announcements(token: str) -> tuple[dict[str, list[dict[str, Any]]], str]:
    api_url = f"https://api.github.com/repos/{ANNOUNCEMENT_REPO}/contents/{ANNOUNCEMENT_FILE_PATH}"
    resp = requests.get(api_url, headers=_github_headers(token), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    file_data = resp.json()
    content = base64.b64decode(file_data["content"]).decode("utf-8")
    payload = normalize_payload(json.loads(content))
    return payload, file_data["sha"]


def update_remote_announcements(token: str, payload: dict[str, list[dict[str, Any]]], sha: str | None) -> None:
    api_url = f"https://api.github.com/repos/{ANNOUNCEMENT_REPO}/contents/{ANNOUNCEMENT_FILE_PATH}"
    normalized = normalize_payload(payload)
    updated_content = json.dumps(normalized, indent=4, ensure_ascii=False) + "\n"
    body = {
        "message": f"Update announcements ({len(normalized['announcements'])} items)",
        "content": base64.b64encode(updated_content.encode("utf-8")).decode("utf-8"),
        "branch": _resolve_default_branch(ANNOUNCEMENT_REPO, token),
    }
    if sha:
        body["sha"] = sha

    resp = requests.put(api_url, headers=_github_headers(token), json=body, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()


class AnnouncementManagerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnnouncementManagerWidget")
        self.announcements: list[dict[str, Any]] = []
        self.remote_sha: str | None = None
        self._init_ui()
        self.load_template()

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        outer_layout.addWidget(self.scroll_area)

        content = QWidget(self.scroll_area)
        self.scroll_area.setWidget(content)

        root_layout = QVBoxLayout(content)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(12)

        title_label = SubtitleLabel("公告管理器", self)
        root_layout.addWidget(title_label)

        token_row = QHBoxLayout()
        token_row.addWidget(StrongBodyLabel("Token:", self))
        self.token_edit = LineEdit(self)
        self.token_edit.setPlaceholderText("GitHub Token（留空则使用环境变量 RELEASE_PAT）")
        self.token_edit.setEchoMode(LineEdit.EchoMode.Password)
        token_row.addWidget(self.token_edit)
        root_layout.addLayout(token_row)

        action_row = QHBoxLayout()
        self.pull_button = PrimaryPushButton("拉取远端", self)
        self.pull_button.clicked.connect(self.pull_remote)
        self.template_button = PushButton("加载模板", self)
        self.template_button.clicked.connect(self.load_template)
        self.new_button = PushButton("新建公告", self)
        self.new_button.clicked.connect(self.clear_form)
        self.delete_button = PushButton("删除选中", self)
        self.delete_button.clicked.connect(self.delete_selected)
        self.publish_button = PrimaryPushButton("发布到远端", self)
        self.publish_button.clicked.connect(self.publish_remote)

        action_row.addWidget(self.pull_button)
        action_row.addWidget(self.template_button)
        action_row.addWidget(self.new_button)
        action_row.addWidget(self.delete_button)
        action_row.addWidget(self.publish_button)
        action_row.addStretch(1)
        root_layout.addLayout(action_row)

        self.status_label = QLabel("当前数据来源：模板", self)
        root_layout.addWidget(self.status_label)

        self.table = TableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "标题", "级别", "开始时间", "结束时间", "发布时间"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.load_selected_to_form)
        self.table.setMinimumHeight(260)
        root_layout.addWidget(self.table)

        form_title = StrongBodyLabel("编辑公告", self)
        root_layout.addWidget(form_title)

        self.id_edit = LineEdit(self)
        self.id_edit.setPlaceholderText("唯一 ID，例如 2026-04-23-service-maintenance")
        root_layout.addWidget(self._with_label("ID", self.id_edit))

        self.title_edit = LineEdit(self)
        self.title_edit.setPlaceholderText("公告标题")
        root_layout.addWidget(self._with_label("标题", self.title_edit))

        self.content_edit = PlainTextEdit(self)
        self.content_edit.setPlaceholderText("公告正文")
        self.content_edit.setFixedHeight(90)
        root_layout.addWidget(self._with_label("正文", self.content_edit))

        meta_row = QHBoxLayout()
        self.severity_combo = ComboBox(self)
        for item in VALID_SEVERITIES:
            self.severity_combo.addItem(item)
        meta_row.addWidget(self._with_label("级别", self.severity_combo))

        self.published_at_edit = LineEdit(self)
        self.published_at_edit.setPlaceholderText("2026-04-23T12:00:00+08:00")
        meta_row.addWidget(self._with_label("发布时间", self.published_at_edit))
        root_layout.addLayout(meta_row)

        time_row = QHBoxLayout()
        self.start_at_edit = LineEdit(self)
        self.start_at_edit.setPlaceholderText("可选，ISO 时间")
        time_row.addWidget(self._with_label("开始时间", self.start_at_edit))

        self.end_at_edit = LineEdit(self)
        self.end_at_edit.setPlaceholderText("可选，ISO 时间")
        time_row.addWidget(self._with_label("结束时间", self.end_at_edit))
        root_layout.addLayout(time_row)

        self.link_edit = LineEdit(self)
        self.link_edit.setPlaceholderText("可选，详情链接")
        root_layout.addWidget(self._with_label("链接", self.link_edit))

        form_action_row = QHBoxLayout()
        self.save_button = PrimaryPushButton("保存到列表", self)
        self.save_button.clicked.connect(self.save_current)
        self.preview_button = PushButton("预览 JSON", self)
        self.preview_button.clicked.connect(self.preview_json)
        form_action_row.addWidget(self.save_button)
        form_action_row.addWidget(self.preview_button)
        form_action_row.addStretch(1)
        root_layout.addLayout(form_action_row)

        self.preview_edit = PlainTextEdit(self)
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setPlaceholderText("这里显示当前公告 JSON")
        self.preview_edit.setFixedHeight(180)
        root_layout.addWidget(self.preview_edit)

    def _with_label(self, text: str, widget: QWidget) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(StrongBodyLabel(text, container))
        layout.addWidget(widget)
        return container

    def _resolve_token(self) -> str:
        token = self.token_edit.text().strip() or os.getenv("RELEASE_PAT", "")
        if not token:
            raise ValueError("未找到 GitHub Token，请输入或设置 RELEASE_PAT")
        return token

    def load_template(self) -> None:
        payload = load_template_payload()
        self.announcements = payload["announcements"]
        self.remote_sha = None
        self.status_label.setText("当前数据来源：模板")
        self.refresh_table()
        self.preview_json()

    def pull_remote(self) -> None:
        try:
            token = self._resolve_token()
            payload, sha = fetch_remote_announcements(token)
            self.announcements = payload["announcements"]
            self.remote_sha = sha
            self.status_label.setText(f"当前数据来源：远端（SHA: {sha[:7]}）")
            self.refresh_table()
            self.preview_json()
            InfoBar.success("成功", "已拉取远端公告", parent=self)
        except Exception as e:
            InfoBar.error("拉取失败", str(e), parent=self, duration=5000)

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.announcements))
        for row, announcement in enumerate(self.announcements):
            values = [
                announcement["id"],
                announcement["title"],
                announcement["severity"],
                announcement["start_at"] or "",
                announcement["end_at"] or "",
                announcement["published_at"],
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))

    def load_selected_to_form(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.announcements):
            return

        announcement = self.announcements[row]
        self.id_edit.setText(announcement["id"])
        self.title_edit.setText(announcement["title"])
        self.content_edit.setPlainText(announcement["content"])
        self.severity_combo.setCurrentText(announcement["severity"])
        self.start_at_edit.setText(announcement["start_at"] or "")
        self.end_at_edit.setText(announcement["end_at"] or "")
        self.published_at_edit.setText(announcement["published_at"])
        self.link_edit.setText(announcement["link"] or "")

    def _collect_form_data(self) -> dict[str, Any]:
        return normalize_announcement(
            {
                "id": self.id_edit.text(),
                "title": self.title_edit.text(),
                "content": self.content_edit.toPlainText(),
                "severity": self.severity_combo.currentText(),
                "start_at": self.start_at_edit.text(),
                "end_at": self.end_at_edit.text(),
                "published_at": self.published_at_edit.text(),
                "link": self.link_edit.text(),
            }
        )

    def save_current(self) -> None:
        try:
            announcement = self._collect_form_data()
            row = self.table.currentRow()

            # 如果存在相同 ID，则更新对应项；否则新增
            existing_index = next(
                (i for i, item in enumerate(self.announcements) if item["id"] == announcement["id"]), None
            )
            if existing_index is not None and row not in (-1, existing_index):
                raise ValueError("已存在相同 ID 的其他公告")

            if row >= 0 and row < len(self.announcements):
                self.announcements[row] = announcement
            elif existing_index is not None:
                self.announcements[existing_index] = announcement
            else:
                self.announcements.append(announcement)

            self.announcements = normalize_payload({"announcements": self.announcements})["announcements"]
            self.refresh_table()
            self.preview_json()
            InfoBar.success("成功", "公告已保存到列表", parent=self)
        except Exception as e:
            InfoBar.error("保存失败", str(e), parent=self, duration=5000)

    def delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.announcements):
            InfoBar.warning("提示", "请先选择一条公告", parent=self)
            return

        del self.announcements[row]
        self.refresh_table()
        self.clear_form()
        self.preview_json()
        InfoBar.success("成功", "已删除选中公告", parent=self)

    def clear_form(self) -> None:
        self.table.clearSelection()
        self.id_edit.clear()
        self.title_edit.clear()
        self.content_edit.clear()
        self.severity_combo.setCurrentText("info")
        self.start_at_edit.clear()
        self.end_at_edit.clear()
        self.published_at_edit.clear()
        self.link_edit.clear()

    def preview_json(self) -> None:
        payload = normalize_payload({"announcements": self.announcements})
        self.preview_edit.setPlainText(json.dumps(payload, indent=4, ensure_ascii=False))

    def publish_remote(self) -> None:
        try:
            token = self._resolve_token()
            payload = normalize_payload({"announcements": self.announcements})
            update_remote_announcements(token, payload, self.remote_sha)
            remote_payload, sha = fetch_remote_announcements(token)
            self.announcements = remote_payload["announcements"]
            self.remote_sha = sha
            self.status_label.setText(f"当前数据来源：远端（SHA: {sha[:7]}）")
            self.refresh_table()
            self.preview_json()
            InfoBar.success("成功", "远端公告已更新", parent=self)
        except Exception as e:
            InfoBar.error("发布失败", str(e), parent=self, duration=5000)


class AnnouncementManagerWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        setTheme(Theme.AUTO)
        self.setWindowIcon(QIcon("src/EasiAuto/resources/icons/EasiAuto.ico"))
        self.setWindowTitle("EasiAuto 公告管理器")
        self.resize(1080, 860)

        self.navigationInterface.setExpandWidth(180)
        self.navigationInterface.setCollapsible(False)

        self.manager_widget = AnnouncementManagerWidget(self)
        self.addSubInterface(self.manager_widget, FluentIcon.INFO, "公告管理")


def cmd_template(_) -> None:
    print(json.dumps(load_template_payload(), indent=4, ensure_ascii=False))


def cmd_pull(args) -> None:
    token = args.token or os.getenv("RELEASE_PAT", "")
    if not token:
        raise ValueError("未找到 GitHub Token，请传入 --token 或设置 RELEASE_PAT")

    payload, _ = fetch_remote_announcements(token)
    print(json.dumps(payload, indent=4, ensure_ascii=False))


def cmd_push(args) -> None:
    token = args.token or os.getenv("RELEASE_PAT", "")
    if not token:
        raise ValueError("未找到 GitHub Token，请传入 --token 或设置 RELEASE_PAT")

    payload = normalize_payload(json.loads(Path(args.file).read_text(encoding="utf-8")))
    sha = None
    if not args.skip_pull:
        _, sha = fetch_remote_announcements(token)
    update_remote_announcements(token, payload, sha)
    print("远端公告已更新")


def cmd_ui(_) -> None:
    app = QApplication(sys.argv)
    translator = FluentTranslator()
    app.installTranslator(translator)
    window = AnnouncementManagerWindow()
    window.show()
    sys.exit(app.exec())


def main() -> None:
    parser = argparse.ArgumentParser(prog="EasiAuto 公告管理器", description="管理远端公告文件")
    subparsers = parser.add_subparsers(title="子命令", dest="command")

    template_parser = subparsers.add_parser("template", help="输出公告模板")
    template_parser.set_defaults(func=cmd_template)

    pull_parser = subparsers.add_parser("pull", help="拉取远端公告")
    pull_parser.add_argument("--token", default="", help="GitHub Token")
    pull_parser.set_defaults(func=cmd_pull)

    push_parser = subparsers.add_parser("push", help="将本地 JSON 推送到远端")
    push_parser.add_argument("--file", required=True, help="本地公告 JSON 文件路径")
    push_parser.add_argument("--token", default="", help="GitHub Token")
    push_parser.add_argument("--skip-pull", action="store_true", help="跳过拉取远端 SHA")
    push_parser.set_defaults(func=cmd_push)

    ui_parser = subparsers.add_parser("ui", help="打开图形界面")
    ui_parser.set_defaults(func=cmd_ui)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_ui(args)


if __name__ == "__main__":
    main()
