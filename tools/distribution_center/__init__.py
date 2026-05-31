import argparse
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon, FluentTranslator, FluentWindow, Theme, setTheme

from ._announcement import AnnouncementManagerWidget, normalize_payload
from ._build import BuildWidget
from ._config import ConfigWidget
from ._release import ReleaseFormWidget
from ._shared import ANNOUNCEMENT_FILE_PATH, ANNOUNCEMENT_REPO, fetch_json_from_repo, put_json_to_repo, resolve_token


class DistributionCenter(FluentWindow):
    def __init__(self):
        super().__init__()
        setTheme(Theme.AUTO)
        self.setWindowIcon(QIcon("src/EasiAuto/resources/icons/EasiAuto.ico"))
        self.setWindowTitle("EasiAuto 发行中心")
        self.resize(900, 720)

        self.navigationInterface.setExpandWidth(160)
        self.navigationInterface.setCollapsible(False)

        self.config_widget = ConfigWidget(self)
        self.build_widget = BuildWidget(self)
        self.release_form_widget = ReleaseFormWidget(self)
        self.announcement_widget = AnnouncementManagerWidget(self)

        self.addSubInterface(self.config_widget, FluentIcon.SETTING, "配置")
        self.addSubInterface(self.build_widget, FluentIcon.DEVELOPER_TOOLS, "构建")
        self.addSubInterface(self.release_form_widget, FluentIcon.UPDATE, "发版")
        self.addSubInterface(self.announcement_widget, FluentIcon.INFO, "公告管理")

        # Auto-fetch announcements on startup if token available
        if resolve_token():
            QTimer.singleShot(500, self.announcement_widget.pull_if_token_available)


# ── CLI commands ───────────────────────────────────────────────────────


def cmd_update_manifest(args):
    token = resolve_token()
    if not token:
        # Allow env var override from CLI arg
        token = args.token or resolve_token()
    if token:
        os.environ["RELEASE_PAT"] = token

    from ._release import update_manifest

    update_manifest(
        dist_dir=Path(args.dist_dir),
        version=args.version,
        is_dev=args.is_dev,
        confirm_required=args.confirm_required,
        desc=args.desc or None,
        highlights=json.loads(args.highlights),
        others=json.loads(args.others),
        push_to_beta=args.push_to_beta,
    )


def cmd_ui(_):
    app = QApplication(sys.argv)
    translator = FluentTranslator()
    app.installTranslator(translator)
    w = DistributionCenter()
    w.show()
    sys.exit(app.exec())


def cmd_pull(args) -> None:
    token = args.token or resolve_token()
    if not token:
        raise ValueError("未找到 GitHub Token，请传入 --token 或设置 RELEASE_PAT")

    payload, _ = fetch_json_from_repo(ANNOUNCEMENT_REPO, ANNOUNCEMENT_FILE_PATH, token)
    print(json.dumps(normalize_payload(payload), indent=4, ensure_ascii=False))


def cmd_push(args) -> None:
    token = args.token or resolve_token()
    if not token:
        raise ValueError("未找到 GitHub Token，请传入 --token 或设置 RELEASE_PAT")

    payload = normalize_payload(json.loads(Path(args.file).read_text(encoding="utf-8")))
    sha = None
    if not args.skip_pull:
        _, sha = fetch_json_from_repo(ANNOUNCEMENT_REPO, ANNOUNCEMENT_FILE_PATH, token)

    put_json_to_repo(
        ANNOUNCEMENT_REPO,
        ANNOUNCEMENT_FILE_PATH,
        sha,
        payload,
        f"Update announcements ({len(payload['announcements'])} items)",
        token,
    )
    print("远端公告已更新")


def main():
    parser = argparse.ArgumentParser(prog="EasiAuto 发行中心", description="统一管理构建、发版与公告")
    subparsers = parser.add_subparsers(title="子命令", dest="command")

    # update-manifest
    p = subparsers.add_parser("update-manifest", help="更新清单")
    p.add_argument("--version", required=True, help="版本号, 如 1.1.0")
    p.add_argument("--is-dev", action="store_true", help="是否为预发布版本")
    p.add_argument("--confirm-required", action="store_true", help="是否需要确认")
    p.add_argument("--desc", default="", help="版本描述内容")
    p.add_argument("--highlights", default="[]", help="JSON 格式的亮点列表")
    p.add_argument("--others", default="[]", help="JSON 格式的其他更新列表")
    p.add_argument("--dist-dir", default="build", help="构建产物所在目录")
    p.add_argument("--push-to-beta", action="store_true", help="正式版同步推送到测试版")
    p.add_argument("--token", default="", help="GitHub Token")
    p.set_defaults(func=cmd_update_manifest)

    # pull
    p = subparsers.add_parser("pull", help="拉取远端公告")
    p.add_argument("--token", default="", help="GitHub Token")
    p.set_defaults(func=cmd_pull)

    # push
    p = subparsers.add_parser("push", help="将本地公告 JSON 推送到远端")
    p.add_argument("--file", required=True, help="本地公告 JSON 文件路径")
    p.add_argument("--token", default="", help="GitHub Token")
    p.add_argument("--skip-pull", action="store_true", help="跳过拉取远端 SHA")
    p.set_defaults(func=cmd_push)

    # ui
    p = subparsers.add_parser("ui", help="打开发行中心图形界面")
    p.set_defaults(func=cmd_ui)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_ui(args)


if __name__ == "__main__":
    main()
