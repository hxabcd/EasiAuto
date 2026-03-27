import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

from packaging.version import Version

from EasiAuto import __version__

# ------ 配置区 ------
APP_NAME = "EasiAuto"
COMPANY_NAME = "HxAbCd"
MAIN = "main.py"
OUTPUT_DIR = Path("build")


VERSION = Version(__version__)


def run_nuitka(build_type: Literal["full", "lite"]):
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
        # "--msvc=latest",
        "--assume-yes-for-downloads",
        "--include-data-dir=resources=resources",
        # ------ 导入控制 ------
        "--enable-plugins=pyside6",
        "--follow-imports",
        "--include-module=comtypes.stream",
        "--include-package=sentry_sdk.integrations",
        "--nofollow-import-to=PySide6.QtPdf",
        "--nofollow-import-to=PySide6.QtDataVisualization",
        "--nofollow-import-to=PySide6.QtOpenGL",
        "--nofollow-import-to=PySide6.QtOpenGLWidgets",
        # ------ 输出 ------
        f"--output-dir={target_dir}",
        f"--output-filename={APP_NAME}.exe",
        "--remove-output",
        # ------ Windows 配置 ------
        "--windows-console-mode=disable",
        "--windows-icon-from-ico=resources/EasiAuto.ico",
        f"--company-name={COMPANY_NAME}",
        f"--product-name={APP_NAME}",
        f"--product-version={VERSION.base_version}",
    ]

    if build_type == "lite":
        print("Building LITE version...")
        cmd.append("--nofollow-import-to=numpy")
    else:
        print("Building FULL version...")

    print(f"Executing command: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        print(f"{build_type.upper()} build succeeded! Output path: {target_dir}")
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(1)

    # FULL 版本手动复制 vendors 目录
    if build_type == "full":
        dist_path = target_dir / "main.dist"
        if Path("vendors").exists():
            dest_vendors = dist_path / "vendors"
            dest_vendors.parent.mkdir(parents=True, exist_ok=True)
            if dest_vendors.exists():
                shutil.rmtree(dest_vendors)
            print(f"Copying vendors to {dest_vendors}...")
            shutil.copytree("vendors", dest_vendors)

    # 删除冗余文件
    if build_type == "lite":
        for item in target_dir.glob("*.dll"):
            if item.name.startswith("qt6pdf"):
                print(f"Removing redundant file: {item}")
                item.unlink()

    # 压缩打包结果
    name = [APP_NAME, f"v{VERSION}"]
    name += "_lite" if build_type == "lite" else ""
    name = "_".join(name)

    zip_path = OUTPUT_DIR / name
    print(f"Creating archive: {zip_path}.zip ...")

    src_dir = target_dir / "main.dist"
    shutil.make_archive(str(zip_path), "zip", src_dir)
    print(f"Archive completed: {zip_path}.zip")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EasiAuto build workflow")
    parser.add_argument("--type", choices=["full", "lite"], default="full")
    args = parser.parse_args()

    run_nuitka(args.type)
