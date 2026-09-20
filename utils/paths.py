import sys
from pathlib import Path


def is_frozen() -> bool:
    """三种情况都要判对：
       ① PyInstaller 打包：sys.frozen = True
       ② Nuitka 编译：模块里有 __compiled__（部分版本也会给 sys.frozen）
       ③ 兜底：sys.executable 不是 python 解释器（名字不是 python*.exe）→ 那它就是打包出来的 exe
    """
    if getattr(sys, "frozen", False):
        return True
    if "__compiled__" in globals():
        return True
    stem = Path(sys.executable).stem.lower()
    return not (stem.startswith("python") or stem.startswith("pytest"))


BASE_DIR = Path(sys.executable).parent if is_frozen() else Path(__file__).resolve().parent.parent


# ★ 数据根目录：被 warehouse/boards.py、utils/dirs.py、utils/site_csv.py 用着，别删
DATA_ROOT = BASE_DIR / "data"
