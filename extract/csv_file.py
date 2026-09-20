"""csv：按指定列（或自动猜列）把每行变成一条文本。"""
import csv
from pathlib import Path

from .common import clean_text, read_text_any

TEXT_COL_HINTS = ("content", "text", "正文", "内容", "摘要", "title", "标题",
                  "body", "comment", "评论")


def _guess_text_cols(fieldnames: list[str]) -> list[str]:
    hits = [c for c in fieldnames if c and c.strip().lower() in TEXT_COL_HINTS]
    return hits


def extract_csv(path: Path, doc_id: str = "", rel: str = "", text_cols=None) -> list[dict]:
    path = Path(path)
    name = path.name
    content, enc = read_text_any(path)  # 复用编码探测
    reader = csv.DictReader(content.splitlines())
    fields = reader.fieldnames or []
    cols = list(text_cols) if text_cols else _guess_text_cols(fields)
    note = f"encoding={enc}"
    if not cols:
        cols = list(fields)  # 兜底：整行拼接
        note += "；没找到正文列，按整行拼接（可用 --text-col 指定）"

    rows = []
    for i, record in enumerate(reader, start=2):
        if cols == list(fields):
            text = " | ".join(f"{k}={v}" for k, v in record.items() if v)
        else:
            text = " ".join(record.get(c, "") or "" for c in cols)
        text=clean_text(text)
        if not text:
            continue
        rows.append({"doc_id": doc_id, "source": name, "path": rel, "type": "csv",
                     "page": i, "text": text, "missing": False, "note": note})
    if not rows:
        rows.append({"doc_id": doc_id, "source": name, "path": rel, "type": "csv",
                     "page": 0, "text": "", "missing": True, "note": "CSV 里没有可用文本"})
    return rows

