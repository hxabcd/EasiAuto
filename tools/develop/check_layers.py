"""分层依赖检查：AGENTS.md「分层约定」的机械校验

按 import 图检查 `src/EasiAuto` 内部各层的依赖方向，以及 UI 工具包的使用范围。
相比 ruff 的 `banned-api`，本脚本能区分「包内自引用」与「跨层引用」，
因此不需要为整层开豁免。

用法：
    uv run python tools/develop/check_layers.py
退出码：0 = 通过；非 0 = 存在违规。
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "EasiAuto"

# 组合根：负责装配与启动，可依赖任意层，也可直接使用 UI 工具包
COMPOSITION_ROOT_MODULES = {"__init__.py", "launcher.py", "cli.py", "main.py"}
# 与 core 同级的无业务原语模块，任何层可用
CORE_PRIMITIVE_MODULES = {"consts.py"}

# 各层允许依赖的层；自身总是允许，组合根不在此表内（它不被任何层依赖）
ALLOWED_LAYERS: dict[str, set[str]] = {
    "core": set(),
    "models": {"core"},
    "runtime": {"core", "models"},
    "integrations": {"core", "models"},
    "services": {"core", "models", "integrations", "runtime"},
    "view": {"core", "models", "integrations", "runtime", "services"},
}

# 仅这些层可直接使用 UI 工具包
UI_LAYERS = {"view", "runtime", "组合根"}
UI_PACKAGES = ("qfluentwidgets",)

COMPOSITION_ROOT = "组合根"


def _layer(parts: tuple[str, ...]) -> str | None:
    """模块路径 → 层名；``None`` 表示未登记（需先在 ALLOWED_LAYERS 中登记）"""
    if not parts:
        return COMPOSITION_ROOT
    head = parts[0]
    if len(parts) > 1:
        return head if head in ALLOWED_LAYERS else None
    stem = f"{head[:-3] if head.endswith('.py') else head}.py"
    if stem in COMPOSITION_ROOT_MODULES:
        return COMPOSITION_ROOT
    if stem in CORE_PRIMITIVE_MODULES:
        return "core"
    return head if head in ALLOWED_LAYERS else None


def _resolve_relative(parts: tuple[str, ...], level: int, module: str | None) -> tuple[str, ...]:
    """把相对导入解析成相对 PACKAGE_ROOT 的模块路径"""
    package = parts[:-1]
    if level > 1:
        package = package[: len(package) - (level - 1)]
    if not module:
        return package
    return (*package, *module.split("."))


def _iter_imports(tree: ast.AST, parts: tuple[str, ...]) -> Iterator[tuple[tuple[str, ...], int]]:
    """产出 (模块路径, 行号)；模块路径不含 `EasiAuto` 前缀，未加 `.py`"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield tuple(alias.name.split(".")), node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                yield _resolve_relative(parts, node.level, node.module), node.lineno
            elif node.module:
                yield tuple(node.module.split(".")), node.lineno


def _iter_sources() -> Iterator[tuple[Path, tuple[str, ...]]]:
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        yield path, path.relative_to(PACKAGE_ROOT).parts
    entry = REPO_ROOT / "main.py"
    if entry.exists():
        yield entry, ("main.py",)


def _check_file(path: Path, parts: tuple[str, ...]) -> Iterator[str]:
    src_layer = _layer(parts)
    rel = path.relative_to(REPO_ROOT).as_posix()
    if src_layer is None:
        yield f"{rel}: 未登记的分层，请在 ALLOWED_LAYERS 中登记"
        return

    for target, lineno in _iter_imports(ast.parse(path.read_text(encoding="utf-8")), parts):
        head = target[0]
        if head in UI_PACKAGES and src_layer not in UI_LAYERS:
            yield f"{rel}:{lineno}: {src_layer} 层不得直接使用 UI 工具包（{'、'.join(UI_PACKAGES)}）"
        if head != "EasiAuto" or len(target) < 2:
            continue
        dst_layer = _layer(target[1:])
        if dst_layer is None:
            yield f"{rel}:{lineno}: 未登记的分层：{'.'.join(target[1:])}，请在 ALLOWED_LAYERS 中登记"
        elif COMPOSITION_ROOT not in (src_layer, dst_layer) and dst_layer not in {
            src_layer,
            *ALLOWED_LAYERS[src_layer],
        }:
            yield f"{rel}:{lineno}: {src_layer} 层不得依赖 {dst_layer} 层"


def main() -> int:
    violations = [v for path, parts in _iter_sources() for v in _check_file(path, parts)]
    if violations:
        sys.stdout.write("分层检查失败：\n")
        for violation in violations:
            sys.stdout.write(f"  {violation}\n")
        return 1
    sys.stdout.write(f"分层检查通过：{len(list(_iter_sources()))} 个文件，0 违规\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
