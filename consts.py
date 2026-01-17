import sys
from pathlib import Path

from packaging.version import Version

VERSION = Version("1.1.0a2")
SENTRY_DSN = "https://992aafe788df5155ed58c1498188ae6b@o4510727360348160.ingest.us.sentry.io/4510727362248704"
MANIFEST_URL = "https://0xabcd.dev/update/EasiAuto.json"

EA_EXECUTABLE = (
    Path(sys.executable)
    if getattr(sys, "frozen", False) or getattr(sys, "nuitka_version", None) is not None
    else Path(__file__).parent / "EasiAuto.exe"
).resolve()
