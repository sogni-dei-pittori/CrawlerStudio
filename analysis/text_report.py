"""文本分析报告：语料总体指标 + 全语料总览图 + 每份文档各 5 张图。

用法：
    python -m analysis.text_report                # 全部文档（默认）
    python -m analysis.text_report --docs 2       # 只给字数最多的前 2 份出分文档图
    python -m analysis.text_report --pie-top 6    # 饼图最多 6 片（其余合并成「其他」）
"""
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from analysis import report as R
from analysis import text as T
from charts.basic import bar_h, bar_v, make_page, pie_top, scatter
from utils.paths import BASE_DIR


def metric_rows(metrics: dict) -> pd.DataFrame:
    """指标表：值统一成好读的数（整数不写成 71725.0）。

    为什么不用 pd.DataFrame([metrics]).T：那种写法会把整列数字统一成 float64，
    CSV 里就出现 71725.0 —— 这是"档案"文件，要给人看的。
    """
    rows = []
    for key, value in metrics.items():
        num = float(value)
        # ★ 写成字符串：一列里混着整数和小数时，pandas 会把整列统一成 float64，
        #   CSV 里就出现 71725.0 这种（给 Excel 看的档案，不该长这样）
        rows.append({"指标": key, "值": str(int(num)) if num.is_integer() else f"{num}"})
    return pd.DataFrame(rows, columns=["指标", "值"])


def load_latest_extract() -> pd.DataFrame:
    """找 data/documents/ 下最新一批的 extracted.csv（和项目里"最新快照"一个思路）。"""
    root = BASE_DIR / "data" / "documents"
    snaps = sorted([d for d in root.glob("*") if (d / "extracted.csv").exists()])
    if not snaps:
        print("还没有抽取结果：先在「文本分析」页选好语料目录、点「① 开始抽取」。")
        raise SystemExit(0)      # 不是错误，是"还没做这一步"，退出码给 0
    csv_path = snaps[-1] / "extracted.csv"
    print(f"读取：{csv_path}")
    df = pd.read_csv(csv_path, keep_default_na=False, dtype={"page": str})
    # ★ 读回来只是字符串，先把两个关键列转成能算的类型（原因见手册 2.4）
    df["missing"] = df["missing"].astype(str).str.strip().str.lower().isin(("true", "1"))
    df["chars"] = pd.to_numeric(df["chars"], errors="coerce").fillna(0).astype(int)
    return df


# ----------------------------------------------------------------- 画图
def build_corpus_charts(tables: dict, top: int = 20) -> list:
    """全语料总览图。

    ⚠️ 这里**故意不做"各文档字数排行"**：那属于"文档之间比大小"，
    交给「分文档」那一套去讲（每份文档 5 张图），总览页只讲整批语料。
    """
    charts = []
    freq = tables["语料_词频Top"]
    sent = tables["语料_句长分布"]
    per_doc = tables["语料_每份文件"]
    missing = tables["语料_缺失明细"]

    if not freq.empty:
        charts.append(bar_h(freq, "词", "count", f"全语料词频 Top{top}（去停用词）", label_max=12))
    if not sent.empty:
        charts.append(bar_v(sent, "bucket", "count", "全语料句子长度分布（字/句）"))
    if len(per_doc) >= 2:          # 只有一份文档时，散点图没有意义
        charts.append(scatter(per_doc, "词数", "去重词汇量", "文件名", "全语料：词数 vs 去重词汇量"))
    if not missing.empty:
        group = missing.groupby("类型").size().reset_index(name="count")
        charts.append(bar_v(group, "类型", "count", "缺失文本分类统计"))
    return charts


def build_doc_charts(name: str, parts: dict, top: int = 20, pie_slices: int = 8) -> list:
    """一份文档的 5 张图。

    ① 词频饼图（占比）② 词频 Top N（排行）③ 句子长度分布
    ④ 平均句子长度（本文件 vs 全语料）⑤ 词数 vs 去重词汇量（本文件两个数并排）
    """
    stem = Path(name).stem
    freq = parts[f"文档_词频_{stem}"]
    sent = parts[f"文档_句长分布_{stem}"]
    avg = parts[f"文档_平均句长_{stem}"]
    tok = parts[f"文档_词数对比_{stem}"]

    charts = []
    if not freq.empty:
        charts.append(pie_top(freq, "词", "count", f"《{name}》词频占比 Top{pie_slices}",
                              top=pie_slices))
        charts.append(bar_h(freq, "词", "count", f"《{name}》词频 Top{top}", top=top, label_max=12))
    if not sent.empty:
        charts.append(bar_v(sent, "bucket", "count", f"《{name}》句子长度分布（字/句）"))
    if not avg.empty:
        charts.append(bar_v(avg, "对象", "平均句长_字", f"《{name}》平均句子长度（对比全语料）"))
    if not tok.empty:
        charts.append(bar_v(tok, "指标", "值", f"《{name}》词数 vs 去重词汇量"))
    return charts


# ----------------------------------------------------------------- 入口
def main() -> int:
    ap = argparse.ArgumentParser(description="语料总体指标 + 图表")
    ap.add_argument("--top", type=int, default=20, help="全语料词频图取前几名")
    ap.add_argument("--doc-top", type=int, default=20, help="单份文档词频图取前几名")
    ap.add_argument("--pie-top", type=int, default=8, help="饼图最多几片，其余合并成「其他」")
    ap.add_argument("--docs", type=int, default=0,
                    help="给前几份文档出「分文档」图（0 = 全部；按字数多的优先）")
    args = ap.parse_args()

    df = load_latest_extract()
    metrics = T.total_counts(df)
    print("=" * 56)
    for k, v in metrics.items():
        print(f"  {k:<24} {v}")
    print("=" * 56)

    per_doc = T.per_document(df)
    tables = {
        "语料_总体指标": metric_rows(metrics),
        "语料_每份文件": per_doc,
        "语料_词频Top": T.word_freq(df, top=args.top),
        "语料_句长分布": T.sentence_length_distribution(df),
        "语料_缺失明细": T.missing_detail(df),
    }

    # ---- 每份文档一套：4 张统计表 → 5 张图 ----
    doc_jobs = []
    docs = per_doc if args.docs <= 0 else per_doc.head(args.docs)
    for _, row in docs.iterrows():
        name = row["文件名"]
        stem = Path(name).stem
        parts = {
            f"文档_词频_{stem}": T.word_freq(df, top=max(args.doc_top, args.pie_top), doc=name),
            f"文档_句长分布_{stem}": T.sentence_length_distribution(T.pick_doc(df, name)),
            f"文档_平均句长_{stem}": T.doc_avg_sentence(df, name),
            f"文档_词数对比_{stem}": T.doc_token_vs_vocab(df, name),
        }
        tables.update(parts)
        doc_jobs.append((name, parts))

    out = BASE_DIR / "reports" / datetime.now().strftime("%Y-%m-%d_%H-%M")
    out.mkdir(parents=True, exist_ok=True)          # ★ 先建目录（踩过这个坑）
    for name, table in tables.items():
        table.to_csv(out / f"{name}.csv", index=False, encoding="utf-8-sig")
        print(f"  {name:<34} {len(table):>4} 行")

    # ---- 落盘 HTML（★ 函数写完必须在这里调用，否则只有 CSV 没有 HTML）----
    corpus_charts = build_corpus_charts(tables, top=args.top)
    if corpus_charts:
        make_page(corpus_charts, "文本分析报告").render(str(out / "文本分析.html"))
    doc_charts = []
    for name, parts in doc_jobs:
        doc_charts.extend(build_doc_charts(name, parts, top=args.doc_top,
                                           pie_slices=args.pie_top))
    if doc_charts:
        make_page(doc_charts, "分文档图").render(str(out / "文本分析_分文档.html"))
    R.copy_assets(out)                              # ★ 拷 echarts.min.js → 断网也能看图
    print(f"图：全语料总览 {len(corpus_charts)} 张 -> 文本分析.html"
          f"；分文档 {len(doc_charts)} 张（{len(doc_jobs)} 份）-> 文本分析_分文档.html")

    # 说明文件：★ 不能用 report.write_meta()，它要 df['date'] / df['snapshot_ts'] 两列
    batch = max((BASE_DIR / "data" / "documents").glob("*/extracted.csv"),
                key=lambda p: p.parent.name).parent.name
    sources = tables["语料_每份文件"]
    (out / "_说明.txt").write_text(
        "\n".join([
            f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
            f"数据来源：data/documents/{batch}/extracted.csv"
            f"（{len(df)} 条，缺失 {int(df['missing'].sum())} 条）",
            f"语料文件 {len(sources)} 份，总字数 {int(sources['字数'].sum())}",
            "",
            "本目录内容：",
            *[f"  {k}.csv —— {len(v)} 行，列：{', '.join(v.columns)}" for k, v in tables.items()],
            f"  文本分析.html —— 全语料总览图（{len(corpus_charts)} 张）",
            f"  文本分析_分文档.html —— 每份文档 5 张图（共 {len(doc_jobs)} 份）",
            "  assets/echarts.min.js —— 离线图表库（断网也能看图）",
        ]),
        encoding="utf-8",
    )
    print(f"输出目录：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
