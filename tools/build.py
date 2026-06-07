import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

from packaging.version import Version

from EasiAuto import __version__

APP_NAME = "EasiAuto"
MAIN = "main.py"
OUTPUT_DIR = Path("build")

VERSION = Version(__version__)


def build_dllpatcher():
    patcher_dir = Path("tools/DllPatcher")
    if not patcher_dir.exists():
        print("DllPatcher directory not found, skipping...")
        return
    print("Building DllPatcher...")
    subprocess.run(
        ["dotnet", "build", "-c", "Release"],
        cwd=str(patcher_dir),
        check=True,
        shell=True,
    )
    dllpatcher_out = Path("tools/DllPatcher/bin/Release/net8.0")
    dest = Path("vendors/DllPatcher")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(dllpatcher_out, dest)
    print("DllPatcher build succeeded.")


def run_pyinstaller(build_type: Literal["full", "lite"]):
    target_dir = OUTPUT_DIR / build_type
    dist_path = target_dir / "dist"

    build_dllpatcher()

    spec_file = target_dir / f"{APP_NAME}.spec"
    if spec_file.exists():
        spec_file.unlink()

    resources_src = str(Path("resources").resolve())
    vendors_src = str(Path("vendors").resolve())

    cmd = [
        "uv",
        "run",
        "pyinstaller",
        MAIN,
        "--onedir",
        "--windowed",
        "--clean",
        f"--name={APP_NAME}",
        f"--distpath={dist_path}",
        f"--workpath={target_dir / 'build'}",
        f"--specpath={target_dir}",
        "--add-data", f"{resources_src}{';'}resources",
        "--add-data", f"{vendors_src}{';'}vendors",
        "--hidden-import", "comtypes.stream",
        "--hidden-import", "sentry_sdk.integrations",
        "--icon=resources/icons/EasiAuto.ico",
    ]

    if build_type == "lite":
        print("Building LITE version...")
        cmd += ["--exclude-module", "numpy", "--exclude-module", "cv2"]
    else:
        print("Building FULL version...")

    print(f"Executing: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        print(f"{build_type.upper()} build succeeded! Output: {dist_path / APP_NAME}")
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(1)

    if build_type == "lite":
        for item in (dist_path / APP_NAME).glob("*.dll"):
            if item.name.startswith("qt6pdf"):
                print(f"Removing redundant file: {item}")
                item.unlink()

    names = [APP_NAME, f"v{VERSION}"]
    if build_type == "lite":
        names.append("_lite")
    zip_name = "_".join(names)
    zip_path = OUTPUT_DIR / zip_name
    print(f"Creating archive: {zip_path}.zip ...")
    shutil.make_archive(str(zip_path), "zip", dist_path / APP_NAME)
    print(f"Archive completed: {zip_path}.zip")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EasiAuto build workflow")
    parser.add_argument("--type", choices=["full", "lite"], default="full")
    args = parser.parse_args()
    run_pyinstaller(args.type)
