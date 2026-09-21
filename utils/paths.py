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


# ★ 在任何代码改 sys.argv 之前先记下原始 argv[0]。
#   为什么必须这样：main.py 的 run_task() 会把 sys.argv 改成 [模块名, ...]（防止 --task 串味），
#   于是 run_daily 这类"子进程里再起子进程"的模块，运行时的 sys.argv[0] 已经不是 exe 路径了 ✗。
ARGV0_AT_IMPORT = sys.argv[0] if sys.argv else ""


def self_exe() -> Path:
    """打包后「我自己」那个可执行文件 —— 用来起子进程（exe 自己当解释器）。

    为什么不能直接用 sys.executable：
      - PyInstaller：它就是真 exe，可以直接用；
      - Nuitka：它会报成 dist 目录下的 python.exe，而那个文件根本不存在
        （实测 main.dist 里只有 CrawlerStudio.exe 和 QtWebEngineProcess.exe），
        拿它去起子进程会直接失败，界面上表现为「启动失败」。
    所以按 .exe + 文件存在两个条件依次试，最后退回 sys.executable（开发环境）。
    """
    exe = Path(sys.executable)
    if exe.suffix.lower() == ".exe" and exe.is_file():
        return exe                       # PyInstaller / 开发环境
    for raw in (ARGV0_AT_IMPORT, sys.argv[0] if sys.argv else ""):
        argv0 = Path(raw)
        if argv0.suffix.lower() == ".exe" and argv0.is_file():
            return argv0.resolve()       # Nuitka：退回真正的 exe（优先用 import 时记下的）
    return exe
