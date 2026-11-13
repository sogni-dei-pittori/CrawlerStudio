"""启动器：打包环境判定、黑窗隐藏、`--task` / `--probe` 子命令。

从原来的 main.py 尾部搬出来。这些逻辑和界面无关，但和「打包后怎么跑起来」
强相关，单独成文件后两者互不干扰：改界面不会碰到子进程协议，
改打包行为也不用在读 900 行 UI 代码里找。
"""
from __future__ import annotations

import sys
from pathlib import Path

from utils.paths import BASE_DIR, is_frozen, self_exe

# ★ 千万不要用 getattr(sys, "frozen", False)：那个属性只有 PyInstaller 会设，
#   Nuitka 编译出来的 exe 没有它 → 在编译版里 FROZEN 会一直是 False，
#   于是黑窗不藏、按钮还会用 -m 去起子进程（等于又弹一个界面）。
#   统一用 utils/paths.is_frozen()：PyInstaller / Nuitka / 直接跑 三种情况都判对。
FROZEN = is_frozen()
# ★ 不能用 sys.executable：Nuitka 会把它报成 dist 目录下的 python.exe（文件不存在）
#   self_exe() 依次试 sys.executable -> sys.argv[0]，三种环境都拿到对的程序
PYTHON = str(self_exe())

# 整个脚本都是顶层代码的模块（import 即执行，不需要 main()）
TOP_LEVEL_MODULES = frozenset({"run_daily"})


def hide_console() -> None:
    """打包后的黑窗藏起来（只藏不关）。

    只在"这个控制台确实是我独占的"时候才藏 —— 从终端里手敲启动时，控制台是那个
    终端窗口的，藏了会把用户的终端（连带报错信息）一起藏掉，出问题就没法排查。
    三条都满足才动手：
      1. 有控制台（双击时 Windows 会给一个，从别的程序里起可能没有）；
      2. 启动我的那个进程没挂在这个控制台上（双击 exe 时父进程是 explorer，它不挂控制台；
         在 cmd / PowerShell 里手敲时，父进程就是那个终端，它挂着 → 不动）；
      3. 控制台上只有我自己（数出来 > 1 说明还有人共用 → 不动）。
    只藏不关：窗口还在 → 子进程的 print 照常工作，运行日志和采集失败判定都不受影响。
    """
    if not FROZEN or sys.platform != "win32":
        return
    import ctypes
    import os

    kernel32 = ctypes.windll.kernel32
    hwnd = kernel32.GetConsoleWindow()
    if not hwnd:
        return  # 压根没有控制台，没什么可藏的
    attached = (ctypes.c_uint32 * 16)()
    count = kernel32.GetConsoleProcessList(attached, 16)
    pids = [attached[i] for i in range(count)]
    if os.getppid() in pids or count > 1:
        return  # 和终端或别的进程共用 → 别动它
    ctypes.windll.user32.ShowWindow(hwnd, 0)


def run_task(module: str, extra: list[str] | None = None) -> int:
    """打包后 exe 自己当解释器：CrawlerStudio.exe --task analysis.report。

    ★ 不能用 runpy.run_module()：Nuitka 编译后的模块加载器没有 get_code()，会报
      `AttributeError: type object 'nuitka_module_loader' has no attribute 'get_code'`。
      所以改成"导入模块 → 调它的 main()"：PyInstaller / Nuitka / 开发环境三种情况一致，
      runpy 那行无害的 RuntimeWarning 也顺带没了。

    约定：**凡是要被 --task 跑的模块，都要提供 `main() -> int`**；
    整个脚本都是顶层代码的（run_daily.py 就是）import 的时候已经跑完，不用 main()。
    """
    import importlib

    # ★ 必须改：否则模块会看到 --task 这些参数（像 run_daily 会把 --task 当成"站点名"）。
    #   但 argv[0] 要保留真正的程序路径 —— 有些模块（run_daily）要在子进程里再起子进程，
    #   它们靠 utils.paths.self_exe() 找自己，而那个函数会看 argv[0] ✗ 不能填模块名。
    sys.argv = [sys.argv[0], *(extra or [])]
    mod = importlib.import_module(module)
    entry = getattr(mod, "main", None)
    if entry is None:
        if module in TOP_LEVEL_MODULES:
            return 0                        # 顶层脚本：import 时已经执行完
        print(f"[错误] {module} 没有 main()，什么都没执行（请给它加一个 main() -> int）")
        return 1
    return int(entry() or 0)


def probe() -> None:
    """诊断输出：CrawlerStudio.exe --probe（看清编译版到底怎么判"我是不是打包版"）。"""
    print("[probe] sys.frozen     =", getattr(sys, "frozen", "（没有这个属性）"))
    print("[probe] __compiled__   =", "__compiled__" in globals())
    print("[probe] sys.executable =", sys.executable)
    print("[probe] BASE_DIR       =", BASE_DIR)
    print("[probe] is_frozen()    =", is_frozen())
    print("[probe] FROZEN         =", FROZEN)
    print("[probe] sys.argv[0]    =", sys.argv[0])
    print("[probe] self_exe()     =", self_exe(), f"（存在：{self_exe().is_file()}）")
    print("[probe] PYTHON         =", PYTHON, f"（存在：{Path(PYTHON).is_file()}）")
    print("[probe] 子进程会用     =", "--task" if FROZEN else "-m")
