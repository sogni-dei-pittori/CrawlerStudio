"""启动时的小扫除 + 数据目录准备：删空目录、清过期锁、保证 data/ 能用。

为什么需要：抓取时如果 robots 拒绝、或者中途失败，SiteCsvStore 已经把
data/<域名>/<时间>/ 建出来了，里面一个文件都没有；攒久了资源管理页里
全是空文件夹，找数据很烦。这里在程序启动时跑一次，顺手把过期的
logs/runner.lock 也清掉。

两条安全线：
  1. 只删"整棵子树里一个文件都没有"的目录，里面还有东西的碰都不碰；
  2. 太新的目录不动（默认 10 分钟内）——免得删掉正在进行的抓取刚建出来的目录。
"""
import time
from pathlib import Path

from utils.paths import BASE_DIR

LOCK_FILE = BASE_DIR / "logs" / "runner.lock"
STALE_LOCK_SECONDS = 30 * 60     # 与 run_daily.LOCK_EXPIRE 保持一致：超过就算上次异常退出
MIN_AGE_SECONDS = 10 * 60        # 空目录的"冷静期"：比这更新的目录不动


def clean_empty_dirs(root=None, min_age=MIN_AGE_SECONDS) -> list[str]:
    """自底向上删掉 root 下"整棵子树都没有文件"的目录，返回删掉的路径。

    root 默认是 data/；root 自己永远不删；删不掉的（被占用、没权限）跳过就行。
    """
    base = Path(root) if root else BASE_DIR / "data"
    if not base.is_dir():
        return []

    base_res = base.resolve()
    now = time.time()
    removed: list[str] = []

    # ★ 先把"目录 + 动手之前的时间"记下来：删子目录会把父目录的修改时间刷成现在，
    #   要是边删边 stat，父目录就会被误判成"太新"漏掉（三层全空只会删掉最里层）。
    entries = []
    for p in base.rglob("*"):
        try:
            if p.is_dir():
                entries.append((p, p.stat().st_mtime))
        except OSError:
            continue

    # 按深度从深到浅：先删子目录，父目录才会变成"空的"
    entries.sort(key=lambda item: len(item[0].parts), reverse=True)
    for d, mtime in entries:
        try:
            if not d.resolve().is_relative_to(base_res):     # ① 越界的（软链接等）不动
                continue
            if now - mtime < min_age:                        # ② 太新：可能是正在抓的，留着
                continue
            if any(d.iterdir()):                             # ③ 还有东西：留着
                continue
            d.rmdir()
        except OSError:
            continue                                         # 删不掉就跳过，不影响别的
        try:
            removed.append(str(d.relative_to(BASE_DIR)))     # 日志里显示 data/xxx 更好读
        except ValueError:
            removed.append(str(d))
    return removed


def clean_stale_lock(max_age=STALE_LOCK_SECONDS):
    """删掉过期的采集锁 → 返回路径；锁还新鲜（说明采集真在跑）或没锁就返回 None。"""
    try:
        if not LOCK_FILE.is_file():
            return None
        if time.time() - LOCK_FILE.stat().st_mtime < max_age:
            return None
        LOCK_FILE.unlink()
        return str(LOCK_FILE)
    except OSError:
        return None


EXAMPLE_NAME = "example"      # data/ 为空时的占位目录名
EXAMPLE_NOTE = """这个目录是占位用的，别当数据看。

抓取结果按「域名 / 时间」分目录存放，例如：
    data/example.com/2026-09-19_10-30/pages.csv        通用网页抓取
    data/top.baidu.com/2026-09-19_10-30/board.csv      百度热搜
    data/tophub.today/2026-09-19_10-30/bilibili.csv    B 站日榜
每个快照目录里还有一个 raw/ 子目录，存最原始的响应（JSON / HTML），永不改动。

这个文件可以删。data/ 里要是又空了，程序下次启动会再建一个。
"""


def ensure_data_root(root=None) -> str:
    """保证 data/ 存在；如果它还是空的，就建 example/ 放个说明文件占位。

    为什么要占位：
      1. 界面「资源管理」页用 QFileSystemModel，根目录不存在（或完全为空）时，
         那一页看起来像卡死了 —— 什么都没有、点也没反应；
      2. 占位目录里放了个文件，所以它"非空"，启动清理（clean_empty_dirs）不会把它删掉。
    返回：建了占位就返回它的相对路径（给日志用），本来就没事就返回空串。
    """
    base = Path(root) if root else BASE_DIR / "data"
    base.mkdir(parents=True, exist_ok=True)

    if any(p.name != EXAMPLE_NAME for p in base.iterdir()):     # 已经有真数据了，别多事
        return ""

    example = base / EXAMPLE_NAME
    example.mkdir(exist_ok=True)
    note = example / "说明.txt"
    if not note.is_file():
        note.write_text(EXAMPLE_NOTE, encoding="utf-8")
    return f"{base.name}/{EXAMPLE_NAME}/说明.txt"


if __name__ == "__main__":
    gone = clean_empty_dirs()
    print(f"空目录：删掉 {len(gone)} 个")
    for item in gone:
        print("   ", item)
    print("过期锁：" + (clean_stale_lock() or "没有"))
    print("数据目录：" + (ensure_data_root() or "里面已经有数据了（不用占位）"))
