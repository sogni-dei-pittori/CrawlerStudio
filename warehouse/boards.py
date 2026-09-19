from pathlib import Path
import pandas as pd
from dataclasses import dataclass

from utils.paths import DATA_ROOT
from utils.schema import BOARD_COLUMNS, order_columns


@dataclass(frozen=True)
class Source:
    source: str  # 平台：baidu / bilibili / douban / juejin / toutiao
    dataset: str  # 数据集标识：baidu_realtime / douban_movie_top250 ...
    domain: str  # data/ 下的一级目录名
    filename: str  # 快照目录里的成品 CSV 文件名
    board: str  # 榜单名（快照里本来就有的那一列）
    via: str  # 数据经由谁获取


SOURCES = [
    Source("baidu", "baidu_realtime", "top.baidu.com", "board.csv", "realtime", "top.baidu.com"),
    Source("bilibili", "bilibili_ranking", "api.bilibili.com", "ranking.csv", "ranking", "api.bilibili.com"),  # 旧，已停用
    Source("bilibili", "bilibili_ranking", "tophub.today", "bilibili.csv", "ranking", "tophub.today"),  # 现行
    Source("douban", "douban_movie_top250", "movie.douban.com", "top250.csv", "top250", "movie.douban.com"),
    Source("douban", "douban_book_top250", "book.douban.com", "top250.csv", "top250", "book.douban.com"),
    Source("douban", "douban_doulist", "www.douban.com", "doulist.csv", "doulist", "www.douban.com"),
    Source("juejin", "juejin_hot", "api.juejin.cn", "hot.csv", "hot", "api.juejin.cn"),
    Source("toutiao", "toutiao_hot", "www.toutiao.com", "hot.csv", "hot", "www.toutiao.com"),
]
DERIVED_COLUMNS = ["dataset", "via", "snapshot_ts", "date"]


def list_snapshots(entry) -> list[Path]:
    """只负责扫某一条记录"""
    domain_dir = DATA_ROOT / entry.domain

    if not domain_dir.is_dir():
        return []

    return sorted(p for p in domain_dir.iterdir()
                  if p.is_dir() and (p / entry.filename).is_file())


def load_one(entry, snap_dir: Path) -> pd.DataFrame:
    """读快照"""
    df = pd.read_csv(snap_dir / entry.filename, encoding="utf-8-sig", keep_default_na=False)  # ① 读
    df["dataset"] = entry.dataset
    if "source" not in df.columns:
        df["source"] = entry.source  # 登记表知道
    if "board" not in df.columns:
        df["board"] = entry.board  # 登记表知道
    if "snapshot" not in df.columns:
        df["snapshot"] = snap_dir.name  # 目录名就是时间戳
    for col in ("score", "category"):
        if col not in df.columns:
            df[col] = ""
    if "via" not in df.columns:
        df["via"] = entry.via
    df["snapshot_ts"] = pd.to_datetime(snap_dir.name, format="%Y-%m-%d_%H-%M")
    df["date"] = df["snapshot_ts"].dt.strftime("%Y-%m-%d")
    return order_columns(df, BOARD_COLUMNS + DERIVED_COLUMNS)


def load_boards(sources=None, datasets=None, since=None, until=None):
    frames = []
    for entry in SOURCES:
        if sources and entry.source not in sources:  # ① 筛平台
            continue
        if datasets and entry.dataset not in datasets:  # 筛数据集
            continue
        for snap_dir in list_snapshots(entry):  # ② 一个快照一帧
            frames.append(load_one(entry, snap_dir))

    if not frames:
        return pd.DataFrame(columns=BOARD_COLUMNS + DERIVED_COLUMNS)

    df = pd.concat(frames, ignore_index=True)  # 拼
    df = df.sort_values(["snapshot_ts", "source", "rank"], kind="stable").reset_index(drop=True)
    if since:
        df = df[df["date"] >= since]  # ④ 时间筛选
    if until:
        df = df[df["date"] <= until]
    return df


def audit() -> dict:
    """体检：磁盘 vs 登记表差异 + 空快照 + 老格式快照。"""
    on_disk = {(d.name, f.name) for d in DATA_ROOT.iterdir() if d.is_dir() for f in d.glob("*/*.csv")}
    registered = {(e.domain, e.filename) for e in SOURCES}

    empty_dirs, others, legacy = [], [], []
    for entry in SOURCES:
        d = DATA_ROOT / entry.domain
        if not d.is_dir():
            continue
        for snap in sorted(p for p in d.iterdir() if p.is_dir()):
            if not (snap / entry.filename).is_file():
                names = sorted(f.name for f in snap.glob("*.csv"))
                (others if names else empty_dirs).append(f"{entry.domain}/{snap.name}: {names}")
                continue
            # 只读表头，不读数据（nrows=0 是个很实用的小技巧）
            cols = pd.read_csv(snap / entry.filename, encoding="utf-8-sig", nrows=0).columns
            if "source" not in cols:
                legacy.append(f"{entry.domain}/{snap.name}")

    return {
        "未登记": sorted(on_disk - registered),
        "登记了但磁盘没有": sorted(registered - on_disk),
        "空快照": empty_dirs,
        "含其他数据集": others,
        "老格式快照": legacy,
    }


if __name__ == "__main__":
    df = load_boards()
    print(df.shape)  # 总行数、总列数
    print(df.groupby(["dataset", "via"]).size())  # ★ 这一行能验证整个设计
    print(df["snapshot_ts"].min(), df["snapshot_ts"].max())
    print(df[["rank", "title", "url", "source", "board", "snapshot", "score", "category"]].isna().sum())
    for k, v in audit().items(): print(f"{k}：{len(v)} 个", v[:3])
