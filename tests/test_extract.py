"""extract/：本地文档 → 「一条文本一行」的表。

抽取层的难点全在边界上：编码猜错就整篇乱码，合并单元格不去重字数就虚高，
扫描版 PDF 没有文本层时要报「缺失」而不是当成空文档。这些都用用例钉住。
"""
from __future__ import annotations

import pytest

from extract.common import clean_text, count_chars, read_text_any
from extract.csv_file import extract_csv
from extract.txtfile import extract_txt


class TestCleanText:
    def test_removes_control_chars(self):
        """PDF 抽出来的文本里塞满 \\x00-\\x1f 这些不可见字符。"""
        assert clean_text("正常\x00文本\x0c内容") == "正常文本内容"

    def test_collapses_whitespace(self):
        assert clean_text("甲   乙\t\t丙") == "甲 乙 丙"

    def test_collapses_fullwidth_and_nbsp_space(self):
        assert clean_text("甲　　乙\xa0丙") == "甲 乙 丙"

    def test_strips_edges(self):
        assert clean_text("  甲乙  ") == "甲乙"

    def test_none_is_safe(self):
        assert clean_text(None) == ""


class TestCountChars:
    def test_counts_with_punctuation(self):
        assert count_chars("甲乙。") == 3

    def test_counts_without_punctuation(self):
        assert count_chars("甲乙。", count_punct=False) == 2

    def test_ignores_whitespace(self):
        assert count_chars("甲 乙\n丙") == 3

    def test_counts_latin_and_digits(self):
        assert count_chars("abc123", count_punct=False) == 6


class TestReadTextAny:
    def test_utf8(self, tmp_path):
        path = tmp_path / "a.txt"
        path.write_text("中文内容", encoding="utf-8")

        text, enc = read_text_any(path)

        assert text == "中文内容"
        assert enc == "utf-8"

    def test_utf8_with_bom_is_labelled(self, tmp_path):
        path = tmp_path / "b.txt"
        path.write_text("中文内容", encoding="utf-8-sig")

        text, enc = read_text_any(path)

        assert text == "中文内容"
        assert "BOM" in enc

    def test_gbk_fallback(self, tmp_path):
        """老的中文 txt 大量是 GBK，猜错就整篇乱码。"""
        path = tmp_path / "c.txt"
        path.write_bytes("中文内容".encode("gbk"))

        text, enc = read_text_any(path)

        assert text == "中文内容"
        assert enc == "gbk"

    def test_undecodable_falls_back_with_replacement(self, tmp_path):
        path = tmp_path / "d.txt"
        path.write_bytes(b"\xff\xfe\x00\xd8")

        text, enc = read_text_any(path)

        assert isinstance(text, str)      # 不抛异常就算通过
        assert "replace" in enc


class TestExtractTxt:
    def test_one_row_per_nonempty_line(self, tmp_path):
        path = tmp_path / "x.txt"
        path.write_text("第一行\n\n第三行\n", encoding="utf-8")

        rows = extract_txt(path)

        assert [r["text"] for r in rows] == ["第一行", "第三行"]
        assert [r["page"] for r in rows] == [1, 3]     # 行号保留原文件位置

    def test_empty_file_still_yields_one_row(self, tmp_path):
        """空文件要产出一条记录，否则上层统计「总文本条数」会漏掉这份文档。"""
        path = tmp_path / "empty.txt"
        path.write_text("\n\n", encoding="utf-8")

        rows = extract_txt(path)

        assert len(rows) == 1
        assert rows[0]["text"] == ""
        assert "没有可用文本" in rows[0]["note"]

    def test_notes_the_detected_encoding(self, tmp_path):
        path = tmp_path / "g.txt"
        path.write_bytes("内容".encode("gbk"))

        assert "encoding=gbk" in extract_txt(path)[0]["note"]


class TestExtractCsv:
    def test_uses_matching_text_column(self, tmp_path):
        path = tmp_path / "t.csv"
        path.write_text("id,content\n1,正文甲\n2,正文乙\n", encoding="utf-8")

        rows = extract_csv(path)

        assert [r["text"] for r in rows] == ["正文甲", "正文乙"]

    def test_falls_back_to_whole_row(self, tmp_path):
        """没有可识别的正文列时按整行拼接，并在 note 里提示。"""
        path = tmp_path / "u.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8")

        rows = extract_csv(path)

        assert "a=1" in rows[0]["text"]
        assert "整行拼接" in rows[0]["note"]

    def test_explicit_text_cols_win(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("id,content,summary\n1,正文,摘要\n", encoding="utf-8")

        rows = extract_csv(path, text_cols=["summary"])

        assert rows[0]["text"] == "摘要"
        assert "正文" not in rows[0]["text"]

    def test_empty_csv_marked_missing(self, tmp_path):
        path = tmp_path / "w.csv"
        path.write_text("content\n", encoding="utf-8")

        rows = extract_csv(path)

        assert rows[0]["missing"] is True

    def test_data_rows_are_not_missing(self, tmp_path):
        path = tmp_path / "x.csv"
        path.write_text("content\n甲\n", encoding="utf-8")

        assert extract_csv(path)[0]["missing"] is False


docx = pytest.importorskip("docx")
from docx import Document  # noqa: E402


class TestExtractDocx:
    @pytest.fixture
    def doc_path(self, tmp_path):
        doc = Document()
        doc.add_paragraph("第一段正文")
        doc.add_paragraph("")
        doc.add_paragraph("第二段正文")

        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "姓名"
        table.cell(0, 1).text = "年龄"
        table.cell(1, 0).text = "张三"
        table.cell(1, 1).text = "30"

        path = tmp_path / "sample.docx"
        doc.save(path)
        return path

    def test_extracts_paragraphs(self, doc_path):
        from extract.docxfile import extract_docx

        rows = extract_docx(doc_path)
        texts = [r["text"] for r in rows]

        assert "第一段正文" in texts
        assert "第二段正文" in texts

    def test_extracts_tables_as_pipe_joined_rows(self, doc_path):
        from extract.docxfile import extract_docx

        rows = extract_docx(doc_path)
        table_lines = [r["text"] for r in rows if r["page"].startswith("t")]

        assert table_lines[0] == "姓名 | 年龄"
        assert table_lines[1] == "张三 | 30"

    def test_merged_cells_not_duplicated(self, tmp_path):
        """合并单元格会让 row.cells 把同一格返回多次，不去重就会出现
        「姓名 | 姓名 | 王五」，字数直接虚高。"""
        doc = Document()
        table = doc.add_table(rows=1, cols=3)
        table.cell(0, 0).text = "姓名"
        table.cell(0, 0).merge(table.cell(0, 1))     # 前两格合并
        table.cell(0, 2).text = "王五"
        path = tmp_path / "merged.docx"
        doc.save(path)

        from extract.docxfile import extract_docx

        text = extract_docx(path)[0]["text"]

        assert text.count("姓名") == 1
        assert text == "姓名 | 王五"

    def test_unreadable_file_reports_missing(self, tmp_path):
        """损坏的 docx 不能让整个批量抽取中断。"""
        path = tmp_path / "broken.docx"
        path.write_bytes(b"not a zip archive")

        from extract.docxfile import extract_docx

        rows = extract_docx(path)

        assert rows[0]["missing"] is True
        assert "无法打开" in rows[0]["note"]

    def test_empty_document_reports_missing(self, tmp_path):
        path = tmp_path / "blank.docx"
        Document().save(path)

        from extract.docxfile import extract_docx

        rows = extract_docx(path)

        assert rows[0]["missing"] is True
