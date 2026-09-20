"""本地语料的文本统计分析。纯函数：输入 DataFrame，输出统计小表；不读文件、不联网、不画图。"""
import re
from collections import Counter

import jieba
import pandas as pd

# ---- 口径常量 ----
MIN_SENT_CHARS = 2          # 少于 2 个字的片段不算句子（滤掉"好。""嗯！"这类噪声）
TTR_MIN_TOKENS = 50         # 词数太少的文档不算 TTR（否则 1 个词也能算出 TTR=1）
TOP_WORDS = 20              # 词频表取前多少名

# 标点与符号：分词后要把这些从"词"里剔掉
PUNCT_RE = re.compile(r"^[\W_]+$", re.UNICODE)
SENT_SPLIT_RE = re.compile(r"[。！？；…!?;]+|\n+")

# 最小停用词表
STOPWORDS = set("""
的 了 和 是 在 有 就 不 也 都 而 及 与 着 或 一个 我们 你们 他们 这 那 这个 那个
上 下 中 里 个 为 以 于 之 其 被 把 让 给 从 到 对 并 但 但是 因为 所以 如果 然后
是 的 地 得 过 很 更 最 会 能 可以 要 说 好 吗 呢 吧 啊 哦 嗯
""".split())

def tokenize(text: str) -> list[str]:
    """分词 + 过筛：去标点、去空白、不做小写化（小写化只在算去重词汇量时用）。"""
    words = jieba.lcut(text or "")
    return [w for w in (w.strip() for w in words) if w and not PUNCT_RE.match(w)]


def normalize(token: str) -> str:
    """归一化：英文小写（中文不受影响）—— 让 "Python" 和 "python" 算同一个词。"""
    return token.lower()

def total_counts(df: pd.DataFrame) -> dict:
    """① 总条数 / 总字数 / 总词数 / 去重词汇量 / 缺失数 —— 一次算完，返回 dict。"""
    texts = df.loc[~df["missing"], "text"].tolist()      # ★ 缺失的文本不进字数/词数
    total_chars = sum(len(re.sub(r"\s+", "", t)) for t in texts)
    total_chars_strict = sum(len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", t)) for t in texts)

    tokens = [t for text in texts for t in tokenize(text)]
    vocab = {normalize(t) for t in tokens}
    content_tokens = [t for t in tokens if normalize(t) not in STOPWORDS]
    vocab_content = {normalize(t) for t in content_tokens}

    sentences = split_sentences(texts)
    sent_chars = [len(re.sub(r"\s+", "", s)) for s in sentences]
    sent_tokens = [len(tokenize(s)) for s in sentences]

    return {
        "总文本条数": int(len(df)),
        "有效文本条数": int((~df["missing"]).sum()),
        "缺失文本数量": int(df["missing"].sum()),
        "总字数": int(total_chars),
        "总字数_只算汉字字母数字": int(total_chars_strict),
        "总词数": int(len(tokens)),
        "去重词汇量": int(len(vocab)),
        "去重词汇量_去停用词": int(len(vocab_content)),
        "句子数": int(len(sentences)),
        "平均句子长度_字": round(sum(sent_chars) / len(sent_chars), 2) if sent_chars else 0.0,
        "平均句子长度_词": round(sum(sent_tokens) / len(sent_tokens), 2) if sent_tokens else 0.0,
        "类型形符比TTR": round(len(vocab) / len(tokens), 4) if tokens else 0.0,
    }


def split_sentences(texts) -> list[str]:
    """② 分句：按中英文句末标点切，长度 < MIN_SENT_CHARS 的片段丢掉。"""
    out = []
    for text in texts:
        for piece in SENT_SPLIT_RE.split(text):
            piece = piece.strip()
            if len(re.sub(r"\s+", "", piece)) >= MIN_SENT_CHARS:
                out.append(piece)
    return out


def missing_detail(df: pd.DataFrame) -> pd.DataFrame:
    """③ 缺失明细：哪份文件、哪个位置、什么原因（三类分开）。"""
    bad = df[df["missing"]].copy()
    if bad.empty:
        return pd.DataFrame(columns=["类型", "文件名", "位置", "原因"])
    def kind(note: str) -> str:
        if "不支持" in note or "另存为" in note:
            return "不支持的类型"
        if "没有再" in note or "没有文本层" in note or "没有可用文本" in note:
            return "抽出来是空的"
        return "抽取失败"
    return pd.DataFrame({
        "类型": bad["note"].map(kind),
        "文件名": bad["source"],
        "位置": bad["page"].astype(str),
        "原因": bad["note"],
    })


def word_freq(df: pd.DataFrame, top: int = TOP_WORDS, drop_stopwords: bool = True,
              doc: str | None = None) -> pd.DataFrame:
    """④ 词频表：给词频图用（列名 bucket/count/pct，和项目里其它统计表一致）。

    doc：只统计某一份文件（文件名或 doc_id），给"单文档词频饼图"用；不传 = 全语料。
    """
    view = df if doc is None else pick_doc(df, doc)
    tokens = [t for text in view.loc[~view["missing"], "text"] for t in tokenize(text)]
    if drop_stopwords:
        tokens = [t for t in tokens if normalize(t) not in STOPWORDS]
    counter = Counter(normalize(t) for t in tokens)
    total = sum(counter.values()) or 1
    rows = [{"词": w, "count": c, "pct": round(c / total * 100, 2)}
            for w, c in counter.most_common(top)]
    return pd.DataFrame(rows, columns=["词", "count", "pct"])


def sentence_length_distribution(df: pd.DataFrame, bins=(0, 10, 20, 30, 50, 80, 10**9)) -> pd.DataFrame:
    """⑤ 句长分布（按字数分箱）—— 分箱用 pd.cut + reindex，保证空档也占一行。"""
    sentences = split_sentences(df.loc[~df["missing"], "text"].tolist())
    lengths = pd.Series([len(re.sub(r"\s+", "", s)) for s in sentences])
    labels = ["0-10", "11-20", "21-30", "31-50", "51-80", "80+"]
    cut = pd.cut(lengths, bins=bins, labels=labels, right=True)
    table = cut.value_counts().reindex(labels, fill_value=0).rename_axis("bucket").reset_index(name="count")
    table["pct"] = (table["count"] / max(len(lengths), 1) * 100).round(2)
    return table


def per_document(df: pd.DataFrame) -> pd.DataFrame:
    """⑥ 每份文件的汇总（画图和论文里"各文档对比"都靠它）。"""
    rows = []
    for (doc_id, source), group in df.groupby(["doc_id", "source"], sort=False):
        good = group[~group["missing"]]
        tokens = [t for text in good["text"] for t in tokenize(text)]
        sentences = split_sentences(good["text"].tolist())
        rows.append({
            "doc_id": doc_id, "文件名": source,
            "类型": group["type"].iloc[0],
            "条数": len(group), "缺失数": int(group["missing"].sum()),
            "字数": int(good["chars"].sum()), "词数": len(tokens),
            "去重词汇量": len({normalize(t) for t in tokens}),
            "句子数": len(sentences),
            "平均句长_字": round(sum(len(re.sub(r"\s+", "", s)) for s in sentences) / len(sentences), 2)
                          if sentences else 0.0,
        })
    return pd.DataFrame(rows).sort_values("字数", ascending=False)


def pick_doc(df: pd.DataFrame, doc: str) -> pd.DataFrame:
    """挑出某一份文件的所有行（doc 传文件名或 doc_id）。"""
    return df[(df["source"] == doc) | (df["doc_id"] == doc)]


def doc_avg_sentence(df: pd.DataFrame, doc: str) -> pd.DataFrame:
    """⑦ 平均句子长度：本文件 vs 全语料（两行，直接能画柱状图）。"""
    def avg(view: pd.DataFrame) -> tuple[float, int]:
        sents = split_sentences(view.loc[~view["missing"], "text"].tolist())
        if not sents:
            return 0.0, 0
        total = sum(len(re.sub(r"\s+", "", s)) for s in sents)
        return round(total / len(sents), 2), len(sents)

    mine, mine_n = avg(pick_doc(df, doc))
    all_, all_n = avg(df)
    return pd.DataFrame([
        {"对象": "本文件", "平均句长_字": mine, "句子数": mine_n},
        {"对象": "全语料", "平均句长_字": all_, "句子数": all_n},
    ])


def doc_token_vs_vocab(df: pd.DataFrame, doc: str) -> pd.DataFrame:
    """⑧ 本文件的 词数 / 去重词汇量（两行并排，一眼看出用词重复度）。"""
    view = pick_doc(df, doc)
    tokens = [t for text in view.loc[~view["missing"], "text"] for t in tokenize(text)]
    return pd.DataFrame([
        {"指标": "词数", "值": len(tokens)},
        {"指标": "去重词汇量", "值": len({normalize(t) for t in tokens})},
    ])
