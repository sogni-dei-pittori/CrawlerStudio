import sys
from pathlib import Path

if getattr(sys, "frozen", False):                     # 打包成 exe 后：数据落在 exe 旁边
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = BASE_DIR / "data"
REPORT_ROOT = BASE_DIR / "reports"