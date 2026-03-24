import sys
from importlib.util import find_spec
from pathlib import Path

IS_DEV = "__compiled__" not in globals()
EA_PREFIX = "[EasiAuto]"
EA_EXECUTABLE = ((Path(sys.executable) if not IS_DEV else Path(sys.argv[0])).parent / "EasiAuto.exe").resolve()
EA_BASEDIR = EA_EXECUTABLE.parent

VENDOR_PATH = EA_BASEDIR / "vendors"

if str(VENDOR_PATH) not in sys.path:
    sys.path.insert(0, str(VENDOR_PATH))

try:
    IS_FULL = bool(find_spec("cv2"))
except (ModuleNotFoundError, ValueError):
    IS_FULL = False
