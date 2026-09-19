# 站点适配台账（sites.md）

> **这份文件干什么用**：每接入一个站点，就在这里记一行。
> 维护时靠它（改版了先查编码/选择器），写论文时它直接是"多源适配"那一节的素材。
> **所有结论都来自实测**，不是网上抄的；没测的一律标"未测"。
>
> 最后更新：2026-09-16
>
> ⚠️ **robots 检查已代码化**：`utils/net.py` 的 `is_allowed(sess, url)`（按域名缓存；404 视为允许；
> 含 `?` 的规则保守拒绝），已接在 `web_crawler.get_html()` 抓取之前。
> **5 个接口脚本还没接** —— 它们的 robots 结论就写在本文件里，接的时候直接用。

---

## 一、已接入（5 个源，7 个数据集）

### 1. 百度热搜

| 项 | 值 |
|---|---|
| 数据目录 | `data/top.baidu.com/` |
| 脚本 | `baidu_api.py` |
| 入口 | `https://top.baidu.com/api/board?platform=wise&tab=realtime` |
| robots | **404（没有 robots.txt）→ 视为允许** |
| 编码 | UTF-8 |
| 反爬 | 只需 `Referer`；无需 cookie；无签名 |
| 数据量 | **51 条**（1 条置顶 + 50 条） |
| 字段映射 | `index→rank`、`word→title`、`url→url`、`labelTagName→category`、`newHotName→tag` |
| 备注 | ① 置顶条目**没有 `index`** → 用 `rank=0`；② `url` 是 `m.baidu.com/s?word=...` **搜索跳转链接，参数即内容**，不能去参数；③ 接口**没有热度值**（`hotTag` 只是 0/1/3 这种小数字）→ `score` 留空 |

### 2. B站全站日榜（数据源：今日热榜 tophub.today）

| 项 | 值 |
|---|---|
| 数据目录 | `data/tophub.today/`（2026-09-16 起）；历史快照仍在 `data/api.bilibili.com/` |
| 脚本 | `bilibili_rank.py`（采集；2026-09-16 由 `bilibili_api.py` **改名** —— 数据来自网页，再叫 api 就名不副实了）+ `parsers/tophub.py`（解析，纯函数） |
| 入口 | `https://tophub.today/n/74KvxwokxM` —— 今日热榜的「哔哩哔哩全站日榜」，**服务端渲染**（146 KB HTML） |
| robots | ✅ `tophub.today/robots.txt` → **HTTP 404（没有该文件）→ 视为允许**；⚠️ 原官方接口域 `api.bilibili.com` 是 `Disallow: /`，**已停用** |
| 编码 | UTF-8 |
| 反爬 | 无（每天 1 个 GET，只需 `Referer`；页面自带"2 分钟前更新"）。**旧接口的三层反爬（Cookie 预热 / Origin / -352 风控）随该接口一并停用** |
| 数据量 | **100 条**（全站日榜） |
| 字段映射 | 行首名次（`1.`）→`rank`、链接文字→`title`、链接→`url`、`div.item-desc`（`830.4万`）→`score`+`heat_text`；额外列 `aid`/`view`/`via`/`board_id`；`category` 为空（tophub 不给分类） |
| 备注 | ① `score` 是播放量的"万"近似值（0.1 万 = 1000），原始文本见 `heat_text`；② **名次与热度不严格单调**（榜首 830.4 万、第 100 名 334.7 万）→ 分析时别假设单调；③ 链接是**老式 av 号**（没有 bvid）→ 与旧接口数据合并时用 `aid` 对齐；④ 页面自称另有官方数据 API「榜眼数据」（本次未用）；⑤ **2026-09-18 实测：`rank` 与播放量的 Spearman = -0.408** → 播放量**不是**排序依据（对比头条的 -1.000） |

> ### ✅ 2026-09-16 已决定并执行：停用官方接口域，改用 `tophub.today`
>
> | 域名 | robots 实测 | 结论 |
> |---|---|---|
> | `api.bilibili.com` | HTTP 200，内容仅 30 字节：`User-agent: *` + `Disallow: /` | ❌ **禁止抓取**（换 Firefox UA 实测同样 `can_fetch=False`，不是针对某个 UA） |
> | `www.bilibili.com` | HTTP 200，只禁 `/medialist/detail/`、`/index.html` | ✅ 允许 |
>
> **影响**：`bilibili_api.py` 当时调的正是 `api.bilibili.com/x/web-interface/ranking/v2`，
> 按本项目「遵守 robots.txt」的原则**不能继续用** —— 这也正是「把 robots 检查写进代码」的直接动因。
>
> **当时的三个选项（A/B/C 见下）→ 最终选了第四个：换一个合规的数据源**：
> - **A（推荐）**：从 `run_daily.py` 的 `TASKS` 里摘掉 B站，脚本留着手动跑。最省事，历史 100 条数据仍在，
>   跨源分析用剩下 4 个源（百度 / 豆瓣 / 掘金 / 头条）也够。
> - **B（2026-09-16 已实测：走不通）**：`www.bilibili.com` 域下的 5 个候选入口 ——
>   `/x/web-interface/ranking/v2`、`/index/rank/all-3-0.json`、`/index/ranking-zone/index-1-0-0.html` 全是 **404**；
>   `/v/popular/rank/all`、`/v/popular/all` 是 **4459 字节的 JS 空壳**（0 个 `bvid`、0 个 `__INITIAL_STATE__`，只有 3 个外链 JS）。
>   页面本身没有任何榜单数据，数据仍由前端 JS 去请求**被禁的 `api.bilibili.com`**。
>   （如果哪天愿意上浏览器渲染，性质会变成「让浏览器去访问网站」，与「脚本直连接口」不同 —— 留作论文里的合规讨论点，现阶段不做。）
> - **C**：保持现状 —— **不推荐**，与这份台账的合规原则自相矛盾。
>
> **已执行（2026-09-16）**：
> - 采集脚本（原 `bilibili_api.py`，同日改名为 **`bilibili_rank.py`**）改写为抓 `tophub.today` 的「哔哩哔哩全站日榜」；新增纯函数解析器 `parsers/tophub.py`
> - 快照目录由 `data/api.bilibili.com/` 改为 `data/tophub.today/`，产物 `bilibili.csv` + `raw/bilibili.html`
> - 数据里新增 `via`（经由谁获取）与 `board_id` 两列 —— 把"换源"这件事**写进数据本身**，核对历史不用靠记忆
> - 首跑验证：100 行、`rank` 1~100 连续、`score` 全为整数、`aid` 100/100 有值
> - **历史数据一个没动**：`data/api.bilibili.com/` 下的旧快照保留备查（`devlog.md` 有记录）

### 3. 豆瓣（3 个域名 / 3 个数据集）

| 项 | 值 |
|---|---|
| 数据目录 | `data/movie.douban.com/`、`data/book.douban.com/`、`data/www.douban.com/` |
| 脚本 | `douban_boards.py` + `parsers/douban.py` |
| 入口 | `top250?start=0,25,…,225`（10 页×25）、`doulist/116238969/?start=0…100`（5 页） |
| robots | `www.douban.com` 允许（只禁搜索类路径） |
| 编码 | UTF-8 |
| 反爬 | 无 WAF；请求间隔 3 秒；豆列里有失效条目要跳过 |
| 数据量 | 电影 **250** / 图书 **250** / 豆列 **100** |
| 字段映射 | `rank/title/info/rating/votes/quote/url`（`rating` 是**评分**，不进 `score`） |
| 备注 | **名次来源三种**：电影在 `<em>`、图书**页面没有**（靠 `rank_offset`）、豆列在 `.pos`；**评分选择器**：电影 `.rating_num`、图书/豆列 `.rating_nums` |

### 4. 稀土掘金热榜

| 项 | 值 |
|---|---|
| 数据目录 | `data/api.juejin.cn/` |
| 脚本 | `juejin_api.py` |
| 入口 | `https://api.juejin.cn/content_api/v1/content/article_rank?category_id=1&type=hot&count=20` |
| robots | `api.juejin.cn/robots.txt` → **404 → 视为允许** |
| 编码 | UTF-8 |
| 反爬 | 只需 `Referer`；无需 cookie、无需预热 |
| 数据量 | **50 条**（`count=20` 参数被忽略） |
| 字段映射 | 列表顺序→`rank`、`content.title`→`title`、`content.content_id` 拼→`url`、`content_counter.hot_rank`→`score`、`content.category_id`→`category`；额外列 `view/like/collect/author` |
| 备注 | ⚠️ 页面是 **JS 壳**（纯文本仅 95 汉字）→ **必须用接口，不能解析 HTML**；结构是**四层嵌套**（`content`/`content_counter`/`author`） |

### 5. 今日头条热榜

| 项 | 值 |
|---|---|
| 数据目录 | `data/www.toutiao.com/` |
| 脚本 | `toutiao_api.py` |
| 入口 | `https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc` |
| robots | 允许（只禁 `/search`、`/amos_land_page/`、`/m1`、`/m3` 等） |
| 编码 | UTF-8 |
| 反爬 | 只需 `Referer`；无需 cookie、无签名 |
| 数据量 | **51 条**（1 置顶 + 50 条） |
| 字段映射 | 列表顺序→`rank`、`Title`→`title`、`Url`→`url`、`HotValue`→`score`、`LabelDesc`→`category`；额外列 `label/cluster_id/query_word` |
| 备注 | ① **置顶在独立的 `fixed_top_data`**（不在 `data` 里），且字段只有 `Id/Title/Url/Schema` **四个** → 用 `make_row()` 统一字段、缺的兜底成空字符串；② `HotValue` 是**字符串**要 `int()`；③ 离线样本：`data/www.toutiao.com/_samples/`；④ **2026-09-18 实测：`rank` 与 `HotValue` 的 Spearman = -1.000** → 热度值**就是**排序依据（跨源比较热度时这条最不能忽略） |

---

## 二、实测后**决定不接入**的（含依据）

| 站点 | robots 结论 | 技术可行性 | 决定与理由 |
|---|---|---|---|
| **微博** `weibo.com` | ❌ `User-agent: *` → **`Disallow: /`**（全站禁止），另有 `Crawl-delay: 1`、`Content-Signal: ai-train=no` | ✅ 1 个 GET 可得 51 条（裸请求 403，需浏览器 UA + Referer） | **不接入**：站方明确禁止。论文可写"因 robots 禁止故未采集"——这是合规设计的证据，不是缺口 |
| **知乎** `zhihu.com` | ❌ `Disallow: /` | 未测（沿用 robots 结论即止） | **不接入**：同上 |
| **抖音** `www.douyin.com` | ✅ **未禁止**（无 `*` 段，只限制特定搜索引擎爬虫） | ⚠️ 1 个 GET 可得 51 条；但 URL 带 `a_bogus`/`msToken`/`verifyFp`/`fp` **签名参数，会过期** | **暂不接入**：长期自动化需要① 逆向签名（**红线，不做**）② 浏览器自动化（太重）③ 官方开放平台；只适合"抓几次做技术验证" |
| **ZOL open-api** `open-api.zol.com.cn` | ❌ `Disallow: /` | ✅ JSON 可得 | **不接入**：① 站方禁止 ② 数据是"**新品发布会日历**"（`subjectTitle`/`startDate`），**不是热榜**，没有名次和热度值 |
| **ZOL 新闻** `news.zol.com.cn` | ✅ **允许**（技术上完全可行） | ✅ 服务端渲染，正文 `#article-content p`；首页 289 条链接 | ❌ **不接入（2026-09-16 项目决定）**：**不是合规问题**，是主动缩减范围、集中做已有 5 个源的分析。**实测结论保留在第三节**，以后想接入随时可用 |

---

## 三、暂缓接入（实测已完成，留档备查）

> **2026-09-16 决定：本项目不接入中关村在线**（`news.zol.com.cn` 与 `open-api.zol.com.cn` 都不接）。
>
> **原因**：不是合规问题 —— `news.zol.com.cn` 的 robots **允许**抓首页与文章页；
> 纯粹是**主动缩减范围**，把精力集中在已有的 5 个源（百度 / B站 / 豆瓣 / 掘金 / 头条）的分析上。
>
> 下面的实测结论**全部保留**：哪天想接入，照着做即可，不用重新探测。

### 中关村在线新闻 `news.zol.com.cn`（暂缓）

| 项 | 值 |
|---|---|
| 计划数据目录 | `data/news.zol.com.cn/` |
| 入口 | 首页 `https://news.zol.com.cn/`（列表）+ 文章页 `/<4位>/<8位>.html` |
| robots | ✅ 允许首页与文章页；**禁止** `/?*`（带参数）、`/new/`、`/bdsuper/`、`/*html?*`、`/index.html`、`/index.shtml`、`/router.php?*`、`/pic/` |
| 编码 | ⚠️ **GBK**（`Content-Type: text/html; charset=gbk`） |
| 反爬 | 无 WAF、**裸 requests 也能拿到一样的内容**；但有**短时连接层限流**（连续快打 8 次后全部 `SSLError`，约 1 分钟自恢复） |
| 结构 | 首页 **289 条**文章链接；正文 = `#article-content p`（与 `.article-cont p`、`div.main p` 等价） |
| 备注 | ① 无 RSS / 无接口（`/rss.xml`、`/feed`、`/api/news` 全 404）；② `/tech/` 回落首页（软 404）；③ ⚠️ **只抓首页列出的链接，不要遍历文章 ID**（`/1248/12481845.html` 是自增 ID，猜 ID 抓等于越过列表页边界）；④ 建议间隔 3~5 秒 |

---

## 四、候选源（robots 允许，未接入）

| 站点 | 类型 | robots 情况 |
|---|---|---|
| IT之家 | 新闻 | 允许（禁 `/ithome/`、`/keywords/`、`/search/` 等） |
| 少数派 | 新闻/评测 | 允许（`*` 段无规则） |
| 36氪 | 商业科技 | 允许（无 `*` 段） |
| 虎嗅 | 商业科技 | 允许（只禁 `*.php$`、`*.rar$` 等） |
| 澎湃 | 时政 | 允许（禁 `/userservice*`、`/comment*` 等） |
| CSDN | 技术社区 | 允许（禁静态资源目录） |
| Solidot | 科技新闻 | 允许（`Allow: /`） |
| 腾讯新闻 | 新闻 | 允许（禁 `/qqfile/`、`/sv1/`） |
| 网易新闻 | 新闻 | 允许（`Disallow:` 空值 = 允许全部） |
| GitHub Trending | 代码趋势 | 允许（禁用户页与 `?tab=` 类） |
| ⚠️ V2EX / Hacker News | 社区/新闻 | **本机网络不通**（`ConnectTimeout`），不是合规问题是网络问题 |

---

## 五、接入新站点时的填写清单

新加一个站点，除了写脚本，还要在**第一节**补一张这样的表，至少包含：

| 必填项 | 为什么要 |
|---|---|
| 数据目录 / 脚本名 | 找得到、改得动 |
| 入口 URL | 改版时第一时间复查 |
| **robots 结论** | 合规证据（论文要用） |
| 编码 | GBK 站点是高风险项（见 `devlog.md` 的 ptcp154 事故） |
| 反爬结论 | 决定要不要预热/伪装/退避重试 |
| 数据量 | 校验用（条数对不上就是解析出问题） |
| 字段映射 | 落到统一 schema（见 `utils/schema.py`） |
| 备注（坑） | 下次不用重新踩 |

---

## 六、接入后的人工核对（代替自动 validate）

> **2026-09-16 决定**：不写 `utils/validate.py`，改用**人工核对**。
> 理由：数据源还少（5 个），自检脚本的收益暂时不如把时间投在分析上。
> 但**每接入一个新站点、或每次改了选择器之后，必须跑一遍下面这个清单**（30 秒）。
>
> ⚠️ 前提是"**人工真的会核对**"。一旦数据源变多（>8 个）或发现漏检，
> 就把它升级成脚本（把下面 4 条变成断言，见 `devlog.md` 待办）。

### 核对四步

| # | 怎么查 | 期望 | 为什么 |
|---|---|---|---|
| 1 | `len(df)` 对比页面/接口的**实际条数** | 一致 | 对不上 = 分页漏了、或有条目被跳过 |
| 2 | `df["rank"].nunique() == len(df)` | 相等 | 名次重复 = 名次算错（图书榜栽过：全是 1–25） |
| 3 | `print(df["title"].head(3))` | 中文正常，不是乱码/西里尔字母 | 编码猜错时**不会报错**（ptcp154 事故） |
| 4 | `df.isna().sum()`，并单看 `score` 列 | 空值只出现在**本来就该空**的列；`score` 是数字 | 空值满屏 = 选择器或字段名写错了 |

**第 5 条（仅新站点）**：查本文件第一节，确认该站点**已登记**（robots / 编码 / 字段映射都填了）。

### 什么时候必须重新核对

| 触发条件 | 为什么 |
|---|---|
| 新接入一个站点 | 第一次必须人工看 |
| 改了选择器 / 改了字段取值 | 改动的直接影响就是数据 |
| 站点改版 | 同上 |
| 采集条数突然变化 | 可能是风控返回了半截数据 |
| 每月抽查一次 | 防止"早就坏了但没人发现" |
