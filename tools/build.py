import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

# --- 配置区 ---
APP_NAME = "EasiAuto"
COMPANY_NAME = "HxAbCd"
MAIN_SCRIPT = "src/EasiAuto/main.py"
ICO_PATH = "src/EasiAuto/resources/EasiAuto.ico"
PYPROJECT_PATH = Path("pyproject.toml")
INIT_FILE_PATH = Path(f"src/{APP_NAME}/__init__.py")
OUTPUT_DIR = Path("build")


def get_version():
    from EasiAuto import __version__

    return __version__


def run_nuitka(base_version, build_type: Literal["full", "lite"]):
    """执行 Nuitka 打包"""
    target_dir = OUTPUT_DIR / build_type

    # Nuitka 基础命令 (使用 uv run 确保环境正确)
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "nuitka",
        # --- 基本参数 ---
        "--standalone",
        "--python-flag=-S",
        # --- 导入控制 ---
        "--follow-imports",
        "--include-module=comtypes.stream",
        "--include-package=sentry_sdk.integrations",
        "--nofollow-import-to=PySide6.QtPdf",
        "--nofollow-import-to=PySide6.QtDataVisualization",
        "--nofollow-import-to=PySide6.QtOpenGL",
        "--nofollow-import-to=PySide6.QtOpenGLWidgets",
        "--nofollow-import-to=PySide6.QtHttpServer",
        # --- 输出及元数据 ---
        f"--output-dir={target_dir}",
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={ICO_PATH}",
        f"--company-name={COMPANY_NAME}",
        f"--product-name={APP_NAME}",
        # 注意：Windows 资源版本号强制要求 X.X.X.X 格式，不能带字母
        f"--product-version={base_version}",
        "--enable-plugins=pyside6",
        # "--include-data-dir=resources=resources",
        f"--output-filename={APP_NAME}.exe",
        "--msvc=latest",
        "--remove-output",
    ]

    # Lite 版特殊处理：排除 OpenCV
    if build_type == "lite":
        print("📦 正在构建 LITE 版...")
        cmd.append("--nofollow-import-to=cv2")
    else:
        print("📦 正在构建 FULL 版...")

    cmd.append(MAIN_SCRIPT)

    print(f"🛠️ 执行命令: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        print(f"✨ {build_type.upper()} 构建成功！导出路径: {target_dir}")
    except subprocess.CalledProcessError as e:
        print(f"❌ 构建失败: {e}")
        sys.exit(1)

    # 删除冗余文件
    if build_type == "lite":
        for item in target_dir.glob("*.dll"):
            if item.name.startswith("opencv_videoio_ffmpeg") or item.name.startswith("qt6pdf"):
                print(f"🧹 删除冗余文件: {item}")
                item.unlink()

    # 压缩打包结果
    zip_name = f"{APP_NAME}_v{base_version}" + "_lite" if build_type == "lite" else ""
    zip_path = OUTPUT_DIR / zip_name

    print(f"📦 正在创建压缩包: {zip_path}.zip ...")

    # Nuitka 的输出在 target_dir/main.dist (Standalone 默认后缀)
    dist_path = target_dir / "main.dist"

    # 如果 Nuitka 没生成 .dist 后缀，就直接用 target_dir
    src_dir = dist_path if dist_path.exists() else target_dir

    shutil.make_archive(str(zip_path), "zip", src_dir)
    print(f"✅ 压缩完成: {zip_path}.zip")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EasiAuto 构建工作流")
    parser.add_argument("--type", choices=["full", "lite"], default="full")
    args = parser.parse_args()

    # 1. 获取基础版本 (如 1.1.0)
    raw_v = get_version()

    # 2. 执行打包
    run_nuitka(raw_v, args.type)
