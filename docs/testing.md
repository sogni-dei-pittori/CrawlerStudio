# 测试与质量报告

> 数据采集于 2026-11-13，环境：Python 3.10 / pandas 2.3 / pytest 9.2 / ruff 0.17。

## 1. 测试总览

```
$ python -m pytest tests/ -q
230 passed in 5.79s
```

230 个用例全部通过，总耗时约 5.8 秒 —— 快到可以在每次改动后随手跑，
这是这套测试能被真正用起来的前提。如果跑一次要五分钟，它就会和
代码一起腐烂。

| 测试文件 | 用例数 | 覆盖对象 | 覆盖的关键行为 |
|---|---|---|---|
| `test_parsers.py` | 35 | `parsers/` | 豆瓣 Top250/豆列、tophub 榜单的 HTML 回归 |
| `test_net.py` | 29 | `utils/net.py` | UA 解析、请求头自洽、robots 判定与缓存 |
| `test_text_analysis.py` | 29 | `analysis/text.py` | 分词、分句、六项指标、词频、缺失分类 |
| `test_extract.py` | 26 | `extract/` | 编码探测、清洗、txt/csv/docx 抽取、合并单元格去重 |
| `test_run_daily.py` | 25 | `run_daily.py` | 参数解析、并发布置、成败判定、锁 |
| `test_analysis.py` | 22 | `analysis/common.py`、`cross.py` | latest 口径、名次跨度、Spearman、LCS、翻新率 |
| `test_http.py` | 19 | `utils/http.py` | 重试策略、按域名限速、并发串行化 |
| `test_launcher.py` | 17 | `main.py`、`gui/launcher.py` | 参数分发、子任务协议 |
| `test_warehouse.py` | 14 | `warehouse/boards.py` | 快照合并、派生列、时间筛选、空仓库、体检 |
| `test_schema.py` | 14 | `utils/schema.py` | URL 规范化（去锚点/保 query）、核心列补齐与排序 |

## 2. 覆盖率

```
$ python -m pytest tests/ --cov --cov-report=term
TOTAL   1333   690   48%
```

48% 的总覆盖率这个数字**单独看没有意义**，要看分布：

| 层 | 模块 | 覆盖率 |
|---|---|---|
| 解析层 | `parsers/douban.py`、`parsers/tophub.py` | **100%** |
| 数据契约 | `utils/schema.py` | **100%** |
| 抽取层 | `extract/common.py`、`txtfile.py` | **100%** |
| | `extract/csv_file.py` | 97% |
| | `extract/docxfile.py` | 91% |
| 网络层 | `utils/net.py` | 96% |
| | `utils/http.py` | 90% |
| 读取层 | `warehouse/boards.py` | 88% |
| 分析层 | `analysis/text.py` | 77% |
| | `analysis/cross.py` | 62% |
| 界面层 | `gui/`、`main.py`、`analysis/live_view.py` | 0%（不计入） |
| 出图层 | `charts/`、`analysis/report.py`、`text_report.py` | 0%（不计入） |

**为什么核心层做得这么高**：这些模块的每个函数都「不报错但会算错」。
`latest()` 忘了筛快照不会抛异常，只会让同一部电影被数 18 次；
LCS 阈值写错不会崩，只会让跨源对比变成一张莫名其妙的表。
这类错误靠人工点界面是发现不了的，只能靠断言具体数值。

**为什么界面层不做**：Qt 界面的价值在交互流程，单元测试需要模拟事件循环、
截图比对，投入产出比很低。改用人工走查 + 结构化拆分
（900 行的类拆成 `gui/main_window.py` 与 `gui/launcher.py`，后者可测）来降低风险。

## 3. 性能基准

### 3.1 采集编排：串行 → 并发

原实现串行跑五个站点，总耗时是各自之和。现在用线程池并发
（各站点仍是独立子进程，互不污染）。

基方法：用各站点的实测耗时量级模拟（豆瓣要翻 10 页，最慢）。

```
串行 2.80s / 并发 1.20s / 加速 2.3x
（理论下限 = 最慢的那个站点 1.20s）
```

加速比恰好达到理论上限，说明并发没有引入额外开销。
真实环境里单站点的网络耗时是秒级，收益会更明显 ——
原来的总耗时是「五个站点之和」，现在是「最慢的那个站点」。

### 3.2 快照合并

```
164 个快照文件 → 20995 行 × 30 列
扫描 0.59s + 解析合并 1.08s = 1.66s
内存 28.3 MB
```

单文件解析 5.3 ms（pandas C 引擎）。尝试过 `engine="python"`（4.3 ms，略快）
和 `engine="pyarrow"`（本项目环境未安装）。

**结论：不优化。** 看板是交互式生成而非实时刷新，1.66 秒可接受；
引入 parquet 缓存会带来「缓存与原始数据不一致」的风险，
而这个项目的核心价值恰恰是「快照可回溯」。
若快照数量增长到千级，再考虑只读筛选后的时间范围。

### 3.3 限速

按域名的最小间隔限速，默认 1 秒。实测并发 4 个线程打同一域名时，
相邻请求间隔均 ≥ 最小间隔（`test_concurrent_callers_are_serialized`），
而不同域名之间完全互不阻塞（`test_different_hosts_do_not_block_each_other`）。

## 4. 静态检查

```
$ python -m ruff check .
All checks passed!
```

对改造前的代码（初始提交）按最终选定的规则集跑一遍，共 **68 条告警**：

| 规则 | 条数 | 含义 | 处理 |
|---|---|---|---|
| I001 | 24 | import 未排序 | 自动修复 |
| W292 | 8 | 文件末尾缺换行 | 自动修复 |
| F401 | 8 | import 了但没用 | 自动修复 |
| RUF046 | 7 | 多余的 `int()` 转换 | 自动修复 |
| W605 | 4 | 字符串里的无效转义 | 手动改 raw string |
| UP031 | 3 | 用 `%` 而不是 f-string | 手动 |
| E701 | 2 | 一行写多条语句 | 手动拆行 |
| B905 | 2 | `zip()` 没写 `strict` | 手动加 `strict=True` |
| B904 | 1 | except 里 raise 丢了异常链 | 手动加 `from exc` |
| SIM / RUF / W291 等 | 9 | 可简化写法、行尾空白等 | 自动 + 复核 |

其中 57 条可自动修复，剩下 11 条需要判断 —— 记录在下一节。

**需要判断的几条，记在这里因为改动有语义**：

- `analysis/text.py` 的停用词表里 `"是"` 和 `"的"` **各写了两遍**。
  `set` 会静默去重所以不影响行为，但说明这段是复制粘贴来的，
  顺便按词性重新分组排版。
- `web_crawler.py` 的 `parsed.port` 是「故意访问它以便触发 ValueError」的写法，
  静态检查认为是无用表达式 —— 加了下划线赋值和注释说明意图。
- `extract/pdf_file.py` 的 `raise RuntimeError(...)` 在 except 里没有 `from exc`，
  丢失了原始异常链，排查时看不到 pypdf 到底报了什么。
- `charts/basic.py` 与 `main.py` 的 `zip()` 没写 `strict` ——
  两个长度不等的序列会被静默截断，`strict=True` 让它当场报错。

**没有跑的**：`ruff format`。项目现有代码是 110 列风格且注释密度高，
强制重排会改动 43 个文件、产生一个巨大的纯空白 diff，
把真正的改动埋掉。现在的策略是「新代码用格式化后的风格，老代码保持原样」。

## 5. 类型检查

```
$ python -m mypy .
Success: no issues found in 44 source files
```

mypy 在核心数据层（`utils/`、`warehouse/`、`analysis/`、`parsers/`、`extract/`、
`run_daily.py`，共 44 个文件）**零告警**。`gui/`、`main.py`、`app.py`、`tests/`
不在检查范围内，理由见下。

**接入 mypy 时修掉的问题**（都是真实缺陷，不只是类型噪音）：

| 位置 | 问题 | 为什么重要 |
|---|---|---|
| `parsers/douban.py` | `select_one()` 可能返回 `None` 却直接 `.get_text()` | **实测一条缺评分的条目会让整页 250 条全部解析失败**，已改为跳过坏条目并补回归用例 |
| `parsers/tophub.py` | `link["href"]` 可能是 list（bs4 多值属性） | 直接切片会 TypeError |
| `utils/http.py` | `send()` 覆写签名与父类不兼容；`get()` 把模块赋给 Session 变量 | 前者破坏 requests 内部调用约定，后者是类型混用 |
| `extract/docxfile.py`、`pdf_file.py` | 可选依赖 `None` 赋值给模块变量 | 显式标注后，未安装依赖的路径不再靠运气 |
| `utils/childio.py` | 参数标成 `dict` 但调用方传的是 `os.environ` | 实际能跑，但类型契约是错的 |

其中 `parsers/douban.py` 那条最有价值 —— 它说明静态检查不只是「让类型好看」，
它发现的是一个只在特定数据下才触发的崩溃。

**为什么先不开 `strict`**：对没有注解历史的项目直接开 `strict` 会得到几百条
「缺少注解」的告警，全是噪音，读到第三天就会开始无视所有 mypy 输出 ——
那等于没有类型检查。当前策略是 `check_untyped_defs = true`
（函数体内部照样检查，能抓出真正的类型错误）但不强制每个函数写注解。
`--strict` 下的差距是「注解覆盖率」，不是「正确性」。

**为什么 GUI 与测试排除在外**：PySide6 的类型桩对 `QProcess` 等 API 描述不准确
（`QProcess.MergedChannels` 在桩里根本不存在），要让它通过得写一串
`# type: ignore`，反而降低可读性；`tests/` 里大量 monkeypatch 替身，
类型天然不严格，对它们做类型检查的收益接近零。

## 6. 已知局限

诚实地记录当前没做到的部分：

1. **没有端到端测试**。真实抓取需要联网且依赖站点可用性，
   测试里全部用替身。这意味着「站点改版导致解析失效」只能靠
   `parsers/` 的固定 HTML 用例发现（结构变了会红），
   而不能自动发现「站点换了新的反爬策略」。
2. **界面层无自动化测试**。拆分后 `gui/launcher.py` 已可测，
   但 `gui/main_window.py` 的 41 个方法仍靠人工走查。
3. **`analysis/live_view.py`（115 行）与出图层未覆盖**。
   这些模块的作用是把统计表拼成 HTML，出错会直接表现为「页面打不开」，
   比较显眼，优先级低于算错数的模块。
4. **并发采集中单个站点仍是串行的**。豆瓣 Top250 要翻 10 页，
   每页之间有间隔（出于礼貌），这部分没有并行化 ——
   对同一站点并发请求本身就不礼貌。
5. **mypy 只覆盖核心数据层**。`gui/`、`main.py`、`tests/` 未纳入检查，
   所以「界面传错参数类型」这类问题仍只能靠运行发现。
6. **`run_daily.py` 的并发只在编排层**。单个站点内部（如豆瓣翻 10 页）
   仍是串行 —— 对同一站点并发请求本身不礼貌，这是有意的限制。
