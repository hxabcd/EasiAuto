import winreg
from pathlib import Path
from typing import Literal

from EasiAuto.models import config


def resolve_easinote_path() -> tuple[Path | None, Literal["registry", "fallback", "manual"]]:
    """获取希沃白板可执行文件路径

    Returns:
        (resolved_path | None, source)
        source: 'registry' — 注册表获取成功
                'fallback' — 注册表失败，使用默认路径
                'manual'   — 使用手动配置路径
    """
    if config.Login.EasiNote.AutoPath:
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Seewo\EasiNote5",
            ) as key:
                path_str = winreg.QueryValueEx(key, "ExePath")[0]
            source = "registry"
        except Exception:
            path_str = r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe"
            source = "fallback"
    else:
        path_str = config.Login.EasiNote.Path
        source = "manual"

    path = Path(path_str).resolve()
    return (path if path.exists() else None, source)
