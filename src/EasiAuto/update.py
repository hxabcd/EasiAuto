from __future__ import annotations

import contextlib
import hashlib
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import requests
from loguru import logger
from packaging.version import Version

from PySide6.QtCore import QObject, QThread, Signal, Slot

from EasiAuto.config import UpdateChannal, config
from EasiAuto.consts import EA_EXECUTABLE, MANIFEST_URL, VERSION

HEADERS = {"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"}
MIRROR = "https://ghproxy.net/"


@dataclass(frozen=True)
class DownloadItem:
    channel: str
    url: str
    sha256: str | None


@dataclass
class ChangeLog:
    description: str
    highlights: list[dict[Literal["name", "description"], str]]
    others: list[str]


@dataclass(frozen=True)
class UpdateDecision:
    available: bool
    target_version: str | None
    confirm_required: bool
    change_log: ChangeLog | None
    downloads: tuple[DownloadItem, ...]


class UpdateError(RuntimeError):
    pass


# -------------------- 独立 Worker 类 --------------------


class CheckWorker(QObject):
    """负责执行检查逻辑的子线程 Worker"""

    finished = Signal(object)  # UpdateDecision
    failed = Signal(str)

    def __init__(self, check_func: Callable[[], UpdateDecision]):
        super().__init__()
        self._func = check_func

    @Slot()
    def run(self):
        try:
            # 在子线程执行耗时的同步网络请求
            result = self._func()
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"检查更新失败: {e}")
            self.failed.emit(str(e))


class DownloadWorker(QObject):
    """负责执行下载逻辑的子线程 Worker"""

    started = Signal(str)  # url
    progress = Signal(int, int)  # done, total
    finished = Signal(str)  # file path
    failed = Signal(str)

    def __init__(
        self,
        download_func: Callable[..., Path],
        item: DownloadItem,
        filename: str | None,
        chunk_size: int,
        cancel_check_func: Callable[[], bool],
    ):
        super().__init__()
        self._func = download_func
        self.item = item
        self.filename = filename
        self.chunk_size = chunk_size
        self._cancel_check_func = cancel_check_func

    @Slot()
    def run(self):
        full_url = (MIRROR + self.item.url) if config.Update.UseMirror else self.item.url
        self.started.emit(full_url)
        try:
            # 定义回调函数将进度转发给信号
            def _on_progress(done: int, total: int):
                self.progress.emit(done, total)

            # 执行同步下载
            path = self._func(
                self.item,
                filename=self.filename,
                chunk_size=self.chunk_size,
                on_progress=_on_progress,
                cancel_checker=self._cancel_check_func,
            )
            self.finished.emit(str(path))
        except Exception as e:
            if "取消" in str(e):
                logger.info("下载任务已取消")
            else:
                logger.error(f"下载更新失败: {e}")
            self.failed.emit(str(e))


# -------------------- 主逻辑类 --------------------


class UpdateChecker(QObject):
    # ================== 外部信号 ==================
    # 异步检查信号
    check_started = Signal()
    check_finished = Signal(UpdateDecision)
    check_failed = Signal(str)

    # 异步下载信号
    download_started = Signal(str)  # url
    download_progress = Signal(int, int)  # bytes_done, total_bytes(-1未知)
    download_finished = Signal(str)  # zip 文件路径
    download_failed = Signal(str)

    def __init__(
        self,
        *,
        package_channel: str = "default",  # default/no_cv/...
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.package_channel = package_channel
        self.session = requests.Session()

        # 线程管理
        self._threads: list[QThread] = []
        self._cancel_download_flag: bool = False
        self._active_response: requests.Response | None = None
        self._update_script_path: Path | None = None

    # ================== 同步 API ==================

    def check(self, force: bool = False) -> UpdateDecision:
        """检查更新"""
        manifest = self._fetch_manifest()
        return self._decide(manifest, force)

    def download_update(
        self,
        item: DownloadItem,
        *,
        filename: str | None = None,
        chunk_size: int = 1024 * 1024,
        on_progress: Callable[[int, int], None] | None = None,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> Path:
        """下载更新"""
        dest_dir = Path(EA_EXECUTABLE.parent / "cache")
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_path = dest_dir / (filename or Path(item.url).name)

        # 1. 检查本地是否存在
        if out_path.exists() and item.sha256 and self._check_sha256(out_path, item.sha256):
            logger.info(f"文件已存在且校验通过，跳过下载: {out_path}")
            if on_progress:
                # 模拟进度完成
                size = out_path.stat().st_size
                on_progress(size, size)
            return out_path

        # 2. 准备下载
        url = (MIRROR + item.url) if config.Update.UseMirror else item.url
        total = -1
        done = 0
        logger.info(f"开始下载更新包: {url}")

        try:
            with self.session.get(
                url,
                headers=HEADERS,
                timeout=180,
                stream=True,
            ) as r:
                self._active_response = r  # 保存引用以便取消

                if r.status_code != 200:
                    raise UpdateError(f"下载失败 HTTP {r.status_code}: {r.text[:200]}")

                total_hdr = r.headers.get("Content-Length")
                total = int(total_hdr) if total_hdr and total_hdr.isdigit() else -1

                h = hashlib.sha256()
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        # 检查取消
                        if cancel_checker and cancel_checker():
                            raise UpdateError("下载已取消")
                        if not chunk:
                            continue

                        f.write(chunk)
                        h.update(chunk)
                        done += len(chunk)

                        if on_progress:
                            on_progress(done, total)

        except (requests.RequestException, OSError) as e:
            # 清理未完成文件
            with contextlib.suppress(Exception):
                out_path.unlink(missing_ok=True)
            # 如果是主动关闭 socket 引发的错误，视为取消
            if self._cancel_download_flag:
                raise UpdateError("下载已取消") from e
            raise UpdateError(f"下载过程中出错: {e!s}") from e
        finally:
            self._active_response = None

        # 3. 校验
        if item.sha256:
            self._verify_sha256(out_path, item.sha256)
            logger.success(f"下载完成并校验通过: {out_path}")
        else:
            logger.success(f"下载完成(无校验): {out_path}")

        return out_path

    def create_update_script(self, zip_path: Path, reopen: bool = True) -> Path:
        """解压更新包并生成批处理脚本"""
        staging = Path(tempfile.mkdtemp(prefix="EasiAuto_update_"))
        extract_dir = staging / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"解压更新包到: {extract_dir}")
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)
        except zipfile.BadZipFile as e:
            raise UpdateError(f"解压失败，文件可能已损坏: {e}")

        extract_root = self._normalize_extract_root(extract_dir)

        target_dir = str(EA_EXECUTABLE.parent)
        script = staging / "apply_update.bat"

        # 构建更新脚本：删除旧文件 -> 复制新文件 -> 重启
        # 注意：这里保留了 config.json, logs, cache
        script_content = [
            "@echo off",
            "chcp 65001",
            "setlocal enabledelayedexpansion",
            "timeout /t 1 /nobreak",  # 等待主程序完全退出
            "",
            f"set TARGET_DIR={target_dir}",
            "",
            # 使用 PowerShell 删除除了保留列表外的文件
            (
                r'powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "'
                r"$t = '%TARGET_DIR%'; "
                r"$keep = @('config.json','logs'); "
                r"Get-ChildItem -LiteralPath $t -Force | Where-Object { $keep -notcontains $_.Name } | "
                r'Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"'
            ),
            "",
            f'robocopy "{extract_root}" "%TARGET_DIR%" /E /MOV',
            f'"{EA_EXECUTABLE}"' if reopen else "",
            "endlocal",
        ]

        script.write_text("\r\n".join(script_content), encoding="utf-8")
        logger.info(f"已生成脚本： {script} ")

        self._update_script_path = script
        return script

    def apply_script(self, zip_path: Path, reopen: bool = True) -> None:
        """执行更新脚本（通常此时应退出主程序）"""

        if sys.argv[0].endswith(".py"):
            logger.critical("检测到开发环境，为防止删除源代码，已禁止执行更新脚本")
            return

        path = self._update_script_path or self.create_update_script(zip_path, reopen=reopen)

        subprocess.Popen(
            str(path),
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    # ================== 异步 API ==================

    def check_async(self, force: bool = False) -> None:
        self._cleanup_threads()

        thread = QThread()
        # 将 check 方法传入 Worker
        worker = CheckWorker(lambda: self.check(force))
        worker.moveToThread(thread)
        thread._worker_ref = worker  # 保存引用

        # 信号转发：Worker -> Self (直接连接)
        worker.finished.connect(self.check_finished)
        worker.failed.connect(self.check_failed)

        # 生命周期管理
        thread.started.connect(self.check_started)
        thread.started.connect(worker.run)

        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)

        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._threads.append(thread)
        thread.start()

    def download_async(
        self,
        item: DownloadItem,
        *,
        filename: str,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        """启动异步下载线程"""
        self._cleanup_threads()
        self._cancel_download_flag = False

        thread = QThread()
        worker = DownloadWorker(
            self.download_update,
            item,
            filename,
            chunk_size,
            lambda: self._cancel_download_flag,  # 传入闭包用于检查状态
        )
        worker.moveToThread(thread)
        thread._worker_ref = worker  # 保存引用

        # 信号转发
        worker.started.connect(self.download_started)
        worker.progress.connect(self.download_progress)
        worker.finished.connect(self.download_finished)
        worker.failed.connect(self.download_failed)

        # 生命周期管理
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._threads.append(thread)
        thread.start()

    def cancel_download(self) -> None:
        """取消当前下载"""
        self._cancel_download_flag = True
        # 强制关闭连接，使 requests 立即抛出异常，不用等待 chunk 读取
        if self._active_response:
            with contextlib.suppress(Exception):
                self._active_response.close()

    # ================== 内部辅助方法 ==================

    def _cleanup_threads(self):
        """清理已结束的线程引用"""
        cleaned_threads = []
        for t in self._threads:
            with contextlib.suppress(RuntimeError):
                if t.isRunning:
                    cleaned_threads.append(t)
        self._threads = cleaned_threads

    def _fetch_manifest(self) -> dict[str, Any]:
        try:
            resp = self.session.get(MANIFEST_URL, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            raise UpdateError(f"网络请求失败：{e!s}") from e

        if resp.status_code != 200:
            raise UpdateError(f"服务器返回错误：{resp.status_code}")

        try:
            return resp.json()
        except ValueError as e:
            raise UpdateError(f"manifest JSON 解析失败：{e!s}") from e

    def _decide(self, manifest: dict[str, Any], force: bool = False) -> UpdateDecision:
        target_key = "latest_dev" if config.Update.Channal == UpdateChannal.DEV else "latest"
        target_ver_str = manifest.get(target_key)

        if not target_ver_str:
            return UpdateDecision(False, None, False, None, ())

        if not force and Version(target_ver_str) <= VERSION:  # 强制检查忽略版本
            return UpdateDecision(False, target_ver_str, False, None, ())

        versions = manifest.get("versions", {})
        target_info = versions.get(target_ver_str, {})

        confirm_required = bool(target_info.get("confirm_required", False))
        changelog = self._build_changelog(manifest, Version(target_ver_str), force=force)

        all_downloads = self._extract_downloads(target_info)
        # 筛选符合当前 package_channel 的下载项
        downloads = tuple(d for d in all_downloads if d.channel == self.package_channel)

        return UpdateDecision(True, target_ver_str, confirm_required, changelog, downloads)

    def _build_changelog(
        self,
        manifest: dict[str, Any],
        target_version: Version,
        force: bool = False,
    ) -> ChangeLog | None:
        versions = manifest.get("versions", {})
        # 获取所有大于当前版本且小于等于目标版本的信息
        in_range: list[str] = []
        for v_str in versions:
            try:
                v = Version(v_str)
                if (VERSION < v <= target_version) or (force and v == target_version):  # 强制获取时，至少展示最新版日志
                    in_range.append(v_str)
            except Exception:
                continue

        # 按版本号倒序排列
        in_range.sort(key=lambda x: Version(x), reverse=True)

        if not in_range:
            return None

        descriptions = []
        highlights = []
        others = []
        for v in in_range:
            info: dict = versions[v]
            if bool(info.get("is_dev")) != (config.Update.Channal == UpdateChannal.DEV):  # 不读取不同通道的更新日志
                continue

            if d := info.get("description"):
                descriptions.append(f"[{v}] {d}")
            if h := info.get("highlights"):
                highlights.extend(h)
            if o := info.get("others"):
                others.extend(o)
        description = "\n".join(descriptions)

        return ChangeLog(description=description, highlights=highlights, others=others)

    def _extract_downloads(self, version_info: dict[str, Any]) -> list[DownloadItem]:
        raw_list = version_info.get("downloads", [])
        result = []
        for item in raw_list:
            if isinstance(item, dict) and item.get("channel") and item.get("url"):
                result.append(
                    DownloadItem(
                        channel=item["channel"],
                        url=item["url"],
                        sha256=item.get("sha256"),
                    )
                )
        return result

    def _check_sha256(self, path: Path, expected_sha256: str) -> bool:
        expected = expected_sha256.lower().strip()
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    h.update(chunk)
            return h.hexdigest().lower() == expected
        except Exception:
            return False

    def _verify_sha256(self, path: Path, expected_sha256: str) -> None:
        if not self._check_sha256(path, expected_sha256):
            # 校验失败删除文件
            with contextlib.suppress(Exception):
                path.unlink(missing_ok=True)
            raise UpdateError("文件 SHA256 校验失败")

    def _normalize_extract_root(self, extract_dir: Path) -> Path:
        """如果解压后只有一层文件夹，则以此文件夹为根，防止套娃"""
        entries = list(extract_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
        return extract_dir

    @staticmethod
    def _quote(s: str) -> str:
        s = str(s)
        if any(c in s for c in ' \t"'):
            return '"' + s.replace('"', '\\"') + '"'
        return s


update_checker = UpdateChecker()
