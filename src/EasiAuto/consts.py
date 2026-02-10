import sys
from pathlib import Path

SENTRY_DSN = "https://992aafe788df5155ed58c1498188ae6b@o4510727360348160.ingest.us.sentry.io/4510727362248704"
MANIFEST_URL = "https://0xabcd.dev/update/EasiAuto.json"

IS_DEV = "__compiled__" not in globals()
EA_PREFIX = "[EasiAuto]"
EA_EXECUTABLE = (Path(sys.executable) if not IS_DEV else Path(__file__).parent / "EasiAuto.exe").resolve()
EA_BASEDIR = EA_EXECUTABLE.parent
