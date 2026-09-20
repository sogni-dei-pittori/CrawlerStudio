"""txt：一行 = 一条文本（空行跳过，但记数）。"""
from pathlib import Path
from .common import clean_text, read_text_any


def extract_txt(path: Path, doc_id: str = "", rel: str = "") -> list[dict]:
    content, enc = read_text_any(path)
    rows = []
    for i, line in enumerate(content.splitlines(), start=1):
        text = clean_text(line)
        if not text:
            continue
        rows.append({
            "doc_id": doc_id, "source": Path(path).name, "path": rel,
            "type": "txt", "page": i, "text": text,
            "missing": False, "note": f"encoding={enc}",
        })
    if not rows:
        rows.append({"doc_id": doc_id, "source": Path(path).name, "path": rel,
                     "type": "txt", "page": 0, "text": "",
                     "missing": False, "note": f"文件没有可用文本（encoding={enc}）",
                     })
    return rows
