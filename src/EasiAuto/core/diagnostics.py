"""运行环境诊断信息收集。"""

from __future__ import annotations

import importlib.metadata
import sys


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
