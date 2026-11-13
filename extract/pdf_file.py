"""pdf：逐页抽文本。只支持文字型 PDF；扫描件按要求记成"缺失"。"""
from pathlib import Path

from .common import clean_text

try:
    import pypdf
except ImportError:      # 可选依赖：没装时抽取函数返回「缺失」记录，而不是让批量处理整体失败
    pypdf = None     # type: ignore[assignment]


def extract_pdf(path: Path, doc_id: str = "", rel: str = "") -> list[dict]:
    path = Path(path)
    name, rows = path.name, []
    if pypdf is None:
        return [{"doc_id": doc_id, "source": name, "path": rel, "type": "pdf",
                 "page": 0, "text": "", "missing": True, "note": "未安装 pypdf"}]
    try:
        reader = pypdf.PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # 第三方库抛什么类型不确定，一律转成可读报错
                raise RuntimeError("PDF 已加密，需要密码") from exc
        total, empty_pages = len(reader.pages), []
        for i, page in enumerate(reader.pages, start=1):
            text = clean_text(page.extract_text() or "")
            if text:
                rows.append({"doc_id": doc_id, "source": name, "path": rel, "type": "pdf",
                             "page": i, "text": text, "missing": False, "note": ""})
            else:
                empty_pages.append(i)  # 空页要记账
    except Exception as exc:
        return [{"doc_id": doc_id, "source": name, "path": rel, "type": "pdf",
                 "page": 0, "text": "", "missing": True,
                 "note": f"读取失败：{type(exc).__name__}: {exc}"}]

    if empty_pages:
        rows.append({"doc_id": doc_id, "source": name, "path": rel, "type": "pdf",
                     "page": 0, "text": "", "missing": True,
                     "note": f"有 {len(empty_pages)} 页没有文本层（可能是扫描图）：第 {empty_pages[:10]} 页"})
    if not rows:
        rows.append({"doc_id": doc_id, "source": name, "path": rel, "type": "pdf",
                     "page": 0, "text": "", "missing": True,
                     "note": f"整份 {total} 页都没有文本层（扫描件），本项目不做 OCR"})

    return rows
