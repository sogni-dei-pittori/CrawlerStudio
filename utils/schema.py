"""数据 schema：统一列名 + 三个小工具，供各采集脚本引用。

约定：
- `rank` 从 1 开始；**置顶条目用 0**
- 核心必填列：`rank` / `title` / `url` / `source` / `board` / `snapshot`
- `url` **只去掉 `#锚点`、域名转小写，保留查询参数**
  （有些站点的查询参数就是内容本身，例如百度的搜索跳转链接 `m.baidu.com/s?word=...`；
   至于"robots 禁止带参数的 URL"，那是**采集层**的判断，不该在这里一刀切掉）
- 空值统一写**空字符串**
- 各站点**特有的字段作为"额外列"保留**，不删不改名（pandas 合并时会按列名自动对齐）
"""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

BOARD_COLUMNS = ["rank", "title", "url", "source", "board", "snapshot", "score", "category"]
PAGE_COLUMNS = ["url", "title", "content", "source", "snapshot", "published_at", "doc_type", "page"]


def snapshot_of(out_dir) -> str:
    """从快照目录名取时间戳（目录名本身就是 %Y-%m-%d_%H-%M）。"""
    return Path(out_dir).name


def clean_url(url: str) -> str:
    """规范化 URL：去掉 #锚点、域名转小写；查询参数保留。"""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, parts.query, ""))


def fill_core(row: dict, source: str, board: str, snapshot: str) -> dict:
    """给一行数据补齐核心列（只保证列存在，不做业务映射）。

    用在"解析器返回的 rows"上最合适：`parsers/` 保持纯函数、不知道来源与快照，
    字段映射由采集层负责。
    """
    row.setdefault("source", source)
    row.setdefault("board", board)
    row.setdefault("snapshot", snapshot)
    row.setdefault("score", "")
    row.setdefault("category", "")
    return row


def order_columns(df, columns):
    """核心列排到前面、顺序统一；站点特有的额外列保留在后面。"""
    extra = [c for c in df.columns if c not in columns]
    return df.reindex(columns=list(columns) + extra)
