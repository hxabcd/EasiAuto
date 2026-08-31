from __future__ import annotations

import hashlib
import importlib.metadata
import os
import signal
import sys
from abc import ABCMeta
from contextlib import suppress
from pathlib import Path
from typing import NoReturn, cast, overload

import psutil
import pywintypes
import win32api
import win32com.client
import win32con
import win32gui
import win32process
from loguru import logger

# win32com.shell 为运行时虚拟包，直接从物理路径 win32comext.shell 导入
from win32comext.shell import shell as win32shell
from win32comext.shell import shellcon as win32shellcon

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

from EasiAuto.consts import (
    EA_BASEDIR,
    EA_EXECUTABLE,
    EA_RESDIR,
)


def desensitize_account(account: str) -> str:
    """对账号进行脱敏，生成一致的哈希值用于统计。
    
    取 SHA256 哈希值的前 16 位十六进制数，确保相同账号产生相同脱敏值。
    """
    return hashlib.sha256(account.encode("utf-8")).hexdigest()[:16]


def get_resource(filename: str):
    """获取资源路径"""
    return str(EA_RESDIR / filename)


def get_scale() -> float:
    """获取当前系统缩放比例"""
    app = cast(QApplication, QApplication.instance())
    if app is None:
        raise RuntimeError("QApplication 未初始化")
    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("无法获取主屏幕信息")
    return screen.devicePixelRatio()


def get_main_display_refresh_rate() -> int:
    """获取主显示器刷新率（Hz），限制在 [30, 240] 内；不可得时回退 60。

    动画帧率应跟随显示器，而不是使用固定值；异常/虚拟显示器可能出现
    离谱数值，因此做上下限约束。
    """
    app = cast(QApplication, QApplication.instance())
    if not app:
        return 60
    screen = app.primaryScreen()
    if screen is None:
        return 60
    try:
        rate = round(screen.refreshRate())
    except Exception:
        return 60
    return max(30, min(rate, 240))


def get_animation_frame_interval() -> int:
    """按主显示器刷新率计算动画帧间隔（毫秒），下限 1ms"""
    return max(1, int(1000 / get_main_display_refresh_rate()))


def get_screen_size() -> tuple[int, int]:
    """获取屏幕尺寸（逻辑坐标）"""
    app = cast(QApplication, QApplication.instance())
    if app is None:
        raise RuntimeError("QApplication 未初始化")
    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("无法获取主屏幕信息")

    geo = screen.geometry()
    return (geo.width(), geo.height())


def get_screen_size_physical() -> tuple[int, int]:
    """获取屏幕尺寸（物理像素）"""
    w, h = get_screen_size()
    scale = get_scale()
    return (int(w * scale), int(h * scale))


class Point:
    """一个点，描述屏幕上的坐标。坐标值恒为整数"""

    scale: float | None = None

    @overload
    def __init__(self, x: int | float, y: int | float) -> None: ...

    @overload
    def __init__(self, x: tuple[int | float, int | float]) -> None: ...

    def __init__(self, x: int | float | tuple[int | float, int | float], y: int | float | None = None):
        if isinstance(x, tuple):
            x_val, y_val = x
        else:
            if y is None:
                raise ValueError("必须传入 y 坐标或一个二元组")
            x_val, y_val = x, y

        if x_val < 0 or y_val < 0:
            raise ValueError("坐标值必须为非负数")

        self.x: int = int(x_val)
        self.y: int = int(y_val)

    def __add__(self, other: Point) -> Point:
        if not isinstance(other, Point):
            return NotImplemented
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Point) -> Point:
        if not isinstance(other, Point):
            return NotImplemented
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, other: int | float) -> Point:
        if not isinstance(other, (int, float)):
            return NotImplemented
        return Point(self.x * other, self.y * other)

    def __rmul__(self, other: int | float) -> Point:
        return self.__mul__(other)

    def __truediv__(self, other: int | float) -> Point:
        return self.__mul__(1 / other)

    def __iter__(self):
        yield self.x
        yield self.y

    def scaled(self) -> Point:
        """获取缩放后的坐标"""
        if Point.scale is None:
            Point.scale = get_scale()
        return Point(self.x * Point.scale, self.y * Point.scale)


def calc_relative_login_window_position(
    position: Point, window_size: tuple[int, int], base_size: tuple[int, int]
) -> Point:
    """计算相对登录窗口的位置

    Args:
        position (Point): 原始位置
        window_size (tuple[int, int]): 窗口大小
        base_size (tuple[int, int]): 原始位置与窗口大小所基于的屏幕分辨率
    """

    screen = Point(get_screen_size_physical())
    base_screen = Point(base_size)
    window = Point(window_size)
    window_position = (base_screen - window) / 2

    rel_position = position - window_position
    scaled_rel_position = rel_position.scaled()
    scaled_top_left = (screen - window.scaled()) / 2
    return scaled_rel_position + scaled_top_left


class QABCMeta(type(QObject), ABCMeta):  # type: ignore
    """QObject 与抽象基类的兼容元类"""


def get_start_menu_programs() -> Path | None:
    """获取开始菜单"程序"文件夹路径，获取失败时返回 None"""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        return Path(shell.SpecialFolders("Programs"))
    except Exception as e:
        logger.error(f"获取开始菜单目录失败: {e}")
        return None


def create_shortcut(
    args: str,
    name: str,
    icon_name: str = "EasiAuto",
    show_result_to: QWidget | None = None,
    folder: str | Path | None = None,
) -> Path | None:
    """创建 EasiAuto 快捷方式

    Args:
        args: 启动参数
        name: 快捷方式名称（不含 .lnk 扩展名）
        icon_name: 图标名称（图标目录下的文件名，不含 .ico 扩展名）
        show_result_to: 创建完成后提示的目标控件，None 则不提示
        folder: 快捷方式存放目录；None 表示桌面

    Returns:
        创建的快捷方式路径；失败返回 None
    """
    try:
        name = name + ".lnk"

        shell = win32com.client.Dispatch("WScript.Shell")
        target_dir = Path(folder) if folder else Path(shell.SpecialFolders("Desktop"))
        target_dir.mkdir(parents=True, exist_ok=True)
        shortcut_path = target_dir / name

        # 如果快捷方式已存在，先删除（解决覆盖保存时的权限问题）
        if shortcut_path.exists():
            shortcut_path.unlink(missing_ok=True)
            logger.debug(f"已删除现有快捷方式: {shortcut_path}")

        logger.info(f"创建快捷方式: {shortcut_path}")

        icon_path = EA_RESDIR / "icons" / f"{icon_name}.ico"
        if not icon_path.exists():
            logger.warning(f"图标文件不存在: {icon_path}, 使用默认图标")
            icon_path = EA_RESDIR / "icons" / "EasiAuto.ico"

        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = str(EA_EXECUTABLE)
        shortcut.Arguments = args
        shortcut.WorkingDirectory = str(EA_BASEDIR)
        shortcut.IconLocation = str(icon_path)
        shortcut.Save()

        logger.success(f"创建成功: {shortcut_path}")
        location = "开始菜单" if folder else "桌面"
        if show_result_to:
            InfoBar.success(
                title="成功",
                content=f"已在{location}创建 {name}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=show_result_to,
            )
        return shortcut_path
    except Exception as e:
        logger.error(f"创建快捷方式失败: {e}")
        if show_result_to:
            InfoBar.error(
                title="创建失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=show_result_to,
            )
        return None


def migrate_desktop_shortcut_icon() -> int:
    """迁移桌面 EasiAuto 快捷方式图标路径到新位置。"""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        desktop_path = Path(shell.SpecialFolders("Desktop"))
    except Exception as e:
        logger.warning(f"获取桌面路径失败，跳过快捷方式图标迁移: {e}")
        return 0

    old_icon_path = EA_RESDIR / "EasiAutoShortcut.ico"
    new_icon_path = EA_RESDIR / "icons" / "EasiAutoShortcut.ico"
    assert new_icon_path.exists()

    migrated_count = 0

    # 扫描桌面所有快捷方式，仅处理目标程序为 EasiAuto 的项。
    for lnk_path in desktop_path.glob("*.lnk"):
        with suppress(Exception):
            shortcut = shell.CreateShortcut(str(lnk_path))

            target_path = (shortcut.TargetPath or "").strip()
            if Path(target_path) != EA_EXECUTABLE:
                continue

            icon_location = (shortcut.IconLocation or "").strip()
            if not icon_location:
                continue
            current_icon_path = icon_location.split(",", 1)[0].strip().strip('"')

            if Path(current_icon_path) == old_icon_path:
                shortcut.IconLocation = f"{new_icon_path},0"
                shortcut.Save()
                migrated_count += 1
            elif Path(current_icon_path) == new_icon_path:
                continue

    if migrated_count > 0:
        logger.success(f"已迁移 {migrated_count} 个桌面快捷方式图标")
    return migrated_count


def switch_window(hwnd: int, press_key: bool = False) -> bool:
    """将窗口切到前台并激活"""
    try:
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
        if win32gui.GetForegroundWindow() == hwnd:
            return True

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)

        if win32gui.GetForegroundWindow() == hwnd:
            return True
        if press_key:  # 模拟 Alt 键以确保系统标记当前为交互状态
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32gui.SetForegroundWindow(hwnd)
            return win32gui.GetForegroundWindow() == hwnd
        return False
    except pywintypes.error as e:
        logger.error(f"切换窗口焦点时发生异常: {e}")
        return False


def get_window_by_title(title: str):
    """通过标题获取窗口"""

    def callback(hwnd, extra):
        if title in win32gui.GetWindowText(hwnd):
            extra.append(hwnd)

    hwnds = []
    # 枚举所有顶层窗口
    win32gui.EnumWindows(callback, hwnds)

    if hwnds:
        logger.success(f"已找到标题包含 '{title}' 的窗口")
        return hwnds
    logger.warning(f"未找到标题包含 '{title}' 的窗口")
    return None


def get_window_by_pid(pid: int, target_title: str, strict: bool = True) -> int | None:
    """根据进程 PID 查找窗口句柄，支持部分标题匹配"""
    hwnd_found = None

    def callback(hwnd, _):
        nonlocal hwnd_found
        _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
        if window_pid == pid:
            window_title = win32gui.GetWindowText(hwnd)
            if (target_title == window_title) if strict else (target_title in window_title):
                hwnd_found = hwnd
                return False  # 找到就停止枚举
        return True

    win32gui.EnumWindows(callback, None)
    return hwnd_found


def kill_process(name: str, force: bool = False, wait: bool = False, timeout: float = 1.0) -> None:
    """终止进程

    Args:
        name (str): 进程名
        force (bool, optional): 强制终止进程
        wait (bool, optional): 等待进程结束（阻塞）
    """
    for process in psutil.process_iter(["name"]):
        if process.info["name"] == f"{name}.exe":
            try:
                if force:
                    process.kill()
                else:
                    process.terminate()
                logger.info(f"已向进程 {name} 发送{'强行' if force else ''}终止信号{', 等待中……' if wait else ''}")

                if wait:
                    try:
                        process.wait(timeout)
                        logger.info(f"成功关闭进程 {name}")
                    except psutil.TimeoutExpired:
                        logger.warning(f"进程 {name} 关闭超时")
            except psutil.NoSuchProcess:
                logger.warning(f"进程 {name} 已不存在")
            except psutil.AccessDenied:
                logger.warning("访问被拒绝, 回退至 taskkill")
                if force:
                    os.system(f'taskkill /f /im "{name}.exe" >nul 2>&1')
                else:
                    os.system(f'taskkill /im "{name}.exe" >nul 2>&1')


def get_third_party_libs() -> list[str]:
    """自动收集当前进程实际导入的第三方库及版本（无需手动维护列表）

    遍历 ``sys.modules`` 中的顶层模块，通过发行包元数据解析名称与版本，
    自动排除标准库与 EasiAuto 自身；元数据缺失时跳过该项。
    开发环境与打包环境均可使用。
    """
    try:
        dist_map = importlib.metadata.packages_distributions()
    except Exception:
        dist_map = {}

    libs: set[tuple[str, str]] = set()
    for module_name in sys.modules:
        top_level = module_name.split(".", 1)[0]
        # 忽略标准库、内建模块、内嵌模块与自身
        if top_level.startswith("_") or top_level in sys.builtin_module_names or top_level in sys.stdlib_module_names:
            continue
        if top_level == "EasiAuto":
            continue

        dist_names = dist_map.get(top_level) or [top_level]
        try:
            version = importlib.metadata.version(dist_names[0])
        except importlib.metadata.PackageNotFoundError:
            continue
        libs.add((dist_names[0], version))

    return [f"{name} ({version})" for name, version in sorted(libs)]


def probe_ci_executable() -> Path | None:
    """探测 ClassIsland 可执行文件位置

    依次探测启动目录、用户开始菜单、桌面（用户与公共）中的快捷方式。
    """
    folders = [
        ("启动目录", win32shellcon.CSIDL_STARTUP),
        ("开始菜单程序", win32shellcon.CSIDL_PROGRAMS),
        ("开始菜单", win32shellcon.CSIDL_STARTMENU),
        ("桌面", win32shellcon.CSIDL_DESKTOPDIRECTORY),
        ("公共桌面", win32shellcon.CSIDL_COMMON_DESKTOPDIRECTORY),
    ]

    try:
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception as e:
        logger.error(f"初始化 WScript.Shell 时出错: {e}")
        return None

    for label, csidl in folders:
        lnk_path = Path(win32shell.SHGetFolderPath(0, csidl, 0, 0)) / "ClassIsland.lnk"
        if not lnk_path.exists():
            continue

        try:
            # 解析快捷方式
            target = Path(shell.CreateShortcut(str(lnk_path)).TargetPath).resolve()
        except Exception as e:
            logger.warning(f"解析 {label} 快捷方式失败 {lnk_path}: {e}")
            continue

        if target.exists():
            logger.info(f"通过快捷方式 {lnk_path} 定位到 ClassIsland: {target}")
            return target

    logger.warning("未能在常用位置找到 ClassIsland")
    return None


def init_exit_signal_handlers() -> None:
    """退出信号处理器"""

    def signal_handler(signum, _):
        logger.debug(f"收到信号 {signal.Signals(signum).name}，退出...")
        stop()

    signal.signal(signal.SIGTERM, signal_handler)  # taskkill
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C


def _reset_signal_handlers() -> None:
    """重置信号处理器为默认状态"""
    try:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass


def restart() -> None:
    """重启程序"""
    logger.debug("重启程序")

    app = QApplication.instance()
    if app:
        _reset_signal_handlers()
        app.quit()
        app.processEvents()

    os.execl(sys.executable, sys.executable, *sys.argv)


def stop(status: int = 0) -> NoReturn:
    """退出程序"""
    logger.info("退出程序...")
    app = QApplication.instance()
    if app:
        app.quit()
        app.processEvents()
    logger.info(f"程序退出({status})")
    sys.exit(status)


def crash() -> NoReturn:
    """崩溃程序"""
    raise Exception("Crash Test")
