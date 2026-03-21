import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import psutil
from loguru import logger

from EasiAuto.common.config import config
from EasiAuto.common.consts import VENDOR_PATH

from .base import BaseAutomator, LoginError

INJECTOR_LAUNCHER = VENDOR_PATH / "Snoop" / "Snoop.InjectorLauncher.x86.exe"
INJECTOR = VENDOR_PATH / "ENLoginInjector.dll"

@dataclass
class InjectTarget:
    """注入任务"""

    class_name: str
    dll_path: Path = INJECTOR
    method_name: str = "Trigger"
    settings: str = ""


class InjectAutomator(BaseAutomator):
    """通过注入希沃白板进程登录"""

    def _find_process(self, exclude_pids: list[int] | None = None) -> psutil.Process | None:
        """寻找希沃主进程，可排除已知的 PID"""
        exclude_pids = exclude_pids or []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info["name"].lower()
                pid = proc.info["pid"]
                if all(("easinote" in name, "browser" not in name, "host" not in name, pid not in exclude_pids)):
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def wait_for_new_process(self, old_pid: int, timeout: float = config.Login.Timeout.EnterLoginUI) -> int | None:
        """等待新进程出现，并返回其 PID"""
        logger.info(f"等待新进程启动 (旧 PID: {old_pid})")
        start_time = time.time()
        while time.time() - start_time < timeout:
            self.check_interruption()
            self.update_progress(f"等待进程出现 ({int(time.time() - start_time)}/{int(timeout)}s)")

            new_proc = self._find_process(exclude_pids=[old_pid])
            if new_proc:
                self.update_progress(f"检测到新进程: {new_proc.info['name']} (PID: {new_proc.pid})")

                time.sleep(config.Login.Timeout.EnterLoginUI)
                return new_proc.pid

            time.sleep(0.2)
        return None

    def inject(self, pid: int, target: InjectTarget):
        """底层注入执行"""
        if not INJECTOR_LAUNCHER.exists():
            raise LoginError("找不到注入器执行文件")

        cmd = [
            str(INJECTOR_LAUNCHER),
            "--targetPID",
            str(pid),
            "--assembly",
            str(target.dll_path.resolve()),
            "--className",
            target.class_name,
            "--methodName",
            target.method_name,
            "--settingsFile",
            target.settings,
            "--verbose",
        ]

        try:
            logger.info(f"正在注入 PID {pid} -> {target.class_name}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            logger.debug(f"输出: {result.stdout}")
            logger.info("注入完成")
        except Exception as e:
            raise LoginError("注入失败") from e

    def login(self):
        """执行完整的注入流程"""

        # 第一阶段：注入登录启动器
        self.check_interruption()
        self.update_progress("注入登录启动器")

        first_proc = self._find_process()
        if not first_proc:
            raise LoginError("初始进程未运行")

        launcher_task = InjectTarget(
            class_name="ENLoginInjector.LoginWindowLauncher",
        )

        if self.inject(first_proc.pid, launcher_task):
            # 第二阶段：等待并注入执行器
            self.check_interruption()
            self.update_progress("等待登录窗口")

            if new_pid := self.wait_for_new_process(old_pid=first_proc.pid):
                self.check_interruption()
                self.update_progress("注入执行器")

                performer_task = InjectTarget(
                    class_name="ENLoginInjector.LoginPerformer",
                    settings=f"{self.account}:{self.password}",
                )
                self.inject(new_pid, performer_task)
            else:
                raise LoginError("未能捕获到登录窗口进程")
