"""本地文档抽取总入口。用法：
    python -m extract.documents 目录            # 抽取（默认目录：桌面\语料 或当前目录）
    python -m extract.documents 目录 --copy-raw # 顺便把原文件复制进快照
"""

import argparse
import hashlib
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from utils.paths import BASE_DIR
from .common import count_chars
from .csv_file import extract_csv
from .docxfile import extract_docx
from .pdf_file import extract_pdf
from .txtfile import extract_txt

# 支持的类型 → 处理函数
HANDLERS = {
    ".txt": extract_txt, ".md": extract_txt,  # 顺手支持 .md
    ".docx": extract_docx,
    ".pdf": extract_pdf,
    ".csv": extract_csv,
}

UNSUPPORTED = {".doc": "老版 .doc 不支持，请先用 Word 另存为 .docx",
               ".xls": "老版 .xls 不支持，请另存为 .xlsx"}
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "dist", "build"}


def sha256_of(path: Path, limit_mb: int = 50) -> str:
    """算文件指纹（超过 limit_mb 的大文件只算前 N MB，够用且快）。"""
    h, read = hashlib.sha256(), 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
            read += len(chunk)
            if read >= limit_mb << 20:
                break
    return h.hexdigest()[:32]


def iter_files(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_dir() or any(part in SKIP_DIRS or part.startswith(".") for part in p.parts):
            continue
        out.append(p)
    return out


def extract_all(root: Path, copy_raw: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    files = iter_files(root)
    rows, listing = [], []
    for i, path in enumerate(files, start=1):
        rel = path.relative_to(root).as_posix()
        doc_id = f"D{i:03d}"
        stat = path.stat()
        listing.append({"doc_id": doc_id, "相对路径": rel, "文件名": path.name,
                        "扩展名": path.suffix.lower(), "大小字节": stat.st_size,
                        "修改时间": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "sha256_32": sha256_of(path)})
        ext = path.suffix.lower()
        handler = HANDLERS.get(ext)
        if handler is None:
            rows.append({"doc_id": doc_id, "source": path.name, "path": rel,
                         "type": ext.lstrip(".") or "未知", "page": 0, "text": "",
                         "missing": True,
                         "note": UNSUPPORTED.get(ext, f"不支持的类型 {ext}")})
            continue
        try:
            rows.extend(handler(path, doc_id, rel))
        except Exception as exc:  # 单份文件出错不能毁掉整批
            rows.append({"doc_id": doc_id, "source": path.name, "path": rel,
                         "type": ext.lstrip("."), "page": 0, "text": "", "missing": True,
                         "note": f"抽取异常：{type(exc).__name__}: {exc}"})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["text"] = df["text"].fillna("")
        df["chars"] = df["text"].map(count_chars)  # 口径只在 common 里定义一次
        df["doc_chars"] = df.groupby("doc_id")["chars"].transform("sum")
        df["extracted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return df, pd.DataFrame(listing)

def main()->int:
    ap=argparse.ArgumentParser(description="把本地文档抽成「一条文本一行」的表")
    ap.add_argument("root",nargs="?",default=str(Path.home()/"Desktop"/"语料"),help="要抽取的目录（默认%（default）s）")
    ap.add_argument("--copy-raw", action="store_true", help="顺便把原文件复制进快照 raw/")
    args=ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"目录不存在：{root}")
        return 1

    df,listing=extract_all(root,args.copy_raw)
    out=BASE_DIR/"data"/"documents"/datetime.now().strftime("%Y-%m-%d_%H-%M")
    out.mkdir(parents=True,exist_ok=True)
    df.to_csv(out / "extracted.csv", index=False, encoding="utf-8-sig")
    listing.to_csv(out / "_文件清单.csv", index=False, encoding="utf-8-sig")

    ok=int((~df["missing"]).sum()) if not df.empty else 0
    print(f"文件 {len(listing)} 份 → 文本条目 {len(df)} 条（有效 {ok}，缺失 {len(df) - ok}）")
    print(f"输出：{out}\\extracted.csv")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())