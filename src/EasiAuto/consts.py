import sys
from importlib.util import find_spec
from pathlib import Path

IS_DEV = "__compiled__" not in globals()
EA_PREFIX = "[EasiAuto]"
EA_EXECUTABLE = (Path(sys.executable) if not IS_DEV else Path(__file__).parent / "EasiAuto.exe").resolve()
EA_BASEDIR = EA_EXECUTABLE.parent

SENTRY_DSN = "https://992aafe788df5155ed58c1498188ae6b@o4510727360348160.ingest.us.sentry.io/4510727362248704"
MANIFEST_URL = "https://0xabcd.dev/update/EasiAuto.json"
# 以防我域名过期，放个指向 Github 的链接作为备份
BACKUP_MANIFEST_URL = (
    "https://raw.githubusercontent.com/hxabcd/0xabcd-log/refs/heads/master/public/update/EasiAuto.json"
)


VENDOR_PATH = (EA_BASEDIR / "vendors") if not IS_DEV else (EA_BASEDIR.parent.parent / "vendors")
INJECTOR_LAUNCHER = VENDOR_PATH / "Snoop" / "Snoop.InjectorLauncher.x86.exe"
INJECTOR = EA_BASEDIR / "extensions" / "ENLoginInjector.dll"

# 为什么放 consts 里面？别管
if str(VENDOR_PATH) not in sys.path:
    sys.path.insert(0, str(VENDOR_PATH))

try:
    IS_FULL = bool(find_spec("cv2"))
except (ModuleNotFoundError, ValueError):
    IS_FULL = False

