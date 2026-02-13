import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

# ------ 配置区 ------
APP_NAME = "EasiAuto"
COMPANY_NAME = "HxAbCd"
MAIN = "src/EasiAuto/main.py"
RESOURCE_DIR = "src/EasiAuto/resources"
EXTENSION_DIR = "src/EasiAuto/extensions"
ICO_PATH = "src/EasiAuto/resources/EasiAuto.ico"
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
        # ------ 基本参数 ------
        f"--main={MAIN}",
        "--mode=standalone",
        "--msvc=latest",
        "--assume-yes-for-downloads",
        f"--include-data-dir={RESOURCE_DIR}=resources",
        # ------ 导入控制 ------
        "--enable-plugins=pyside6",
        "--follow-imports",
        "--include-module=comtypes.stream",
        "--include-package=sentry_sdk.integrations",
        "--nofollow-import-to=PySide6.QtPdf",
        "--nofollow-import-to=PySide6.QtNetwork",
        "--nofollow-import-to=PySide6.QtDataVisualization",
        "--nofollow-import-to=PySide6.QtOpenGL",
        "--nofollow-import-to=PySide6.QtOpenGLWidgets",
        # ------ 输出 ------
        f"--output-dir={target_dir}",
        f"--output-filename={APP_NAME}.exe",
        "--remove-output",
        # ------ Windows 配置 ------
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={ICO_PATH}",
        f"--company-name={COMPANY_NAME}",
        f"--product-name={APP_NAME}",
        f"--product-version={base_version}",
    ]

    if build_type == "lite":
        print("Building LITE version...")
        cmd.append("--nofollow-import-to=numpy")
    else:
        print("Building FULL version...")
        cmd.append("--include-data-files=vendors/cv2.cp313-win_amd64.pyd=cv2.pyd")
        cmd.append(f"--include-data-dir={EXTENSION_DIR}=extensions")
        cmd.append("--include-data-dir=vendors/Snoop=vendors/Snoop")

    print(f"Executing command: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        print(f"{build_type.upper()} build succeeded! Output path: {target_dir}")
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(1)

    # 删除冗余文件
    if build_type == "lite":
        for item in target_dir.glob("*.dll"):
            if item.name.startswith("qt6pdf"):
                print(f"Removing redundant file: {item}")
                item.unlink()

    # 压缩打包结果
    zip_name = f"{APP_NAME}_v{base_version}" + ("_lite" if build_type == "lite" else "")
    zip_path = OUTPUT_DIR / zip_name

    print(f"Creating archive: {zip_path}.zip ...")

    # Nuitka 的输出在 target_dir/main.dist (Standalone 默认后缀)
    dist_path = target_dir / "main.dist"

    # 如果 Nuitka 没生成 .dist 后缀，就直接用 target_dir
    src_dir = dist_path if dist_path.exists() else target_dir

    shutil.make_archive(str(zip_path), "zip", src_dir)
    print(f"Archive completed: {zip_path}.zip")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EasiAuto build workflow")
    parser.add_argument("--type", choices=["full", "lite"], default="full")
    args = parser.parse_args()

    # 1. 获取基础版本 (如 1.1.0)
    raw_v = get_version()

    # 2. 执行打包
    run_nuitka(raw_v, args.type)
