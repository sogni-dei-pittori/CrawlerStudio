# crawler · 榜单采集与分析工具

一个把「多站点榜单采集 → 快照归档 → 统一读取 → 统计分析 → 图表看板」串起来的 Python 项目，
另可对本地文档（docx / txt / md / csv / 文字型 PDF）做语料文本分析；
带 PySide6 桌面端，用 Nuitka 编译为免安装程序，并提供 Inno Setup 安装包。

> 当前版本 **0.2.0**
> 打包配置：`CrawlerStudio.spec`（PyInstaller）／`tools\build_nuitka.bat`（Nuitka）／`tools\installer\CrawlerStudio.iss`（安装包）

## 功能

- **采集**
  - 站点采集：百度热搜、B 站全站日榜、豆瓣电影/读书 Top250 与豆列、掘金热榜、今日头条热榜
  - 通用网页采集：输入任意网址，抓取主页并可继续抓站内子页，正文清洗后存档
  - 请求前检查目标站点 `robots.txt`，不允许的域名直接跳过
- **归档**：原始响应（JSON / HTML）与解析结果（CSV）按「域名 / 时间」分快照存放，解析规则变更后可离线重跑
- **读取层**：将分散在各快照的 CSV 合并为一张统一长表，补充数据集、来源、时间等派生列
- **分析**：单源统计（评分分布、年代分布、票数与播放量增长、作者上榜次数、标签构成等）+ 跨源比对（榜单覆盖、同日 Top、同话题、榜单翻新速度）
- **图表与报告**：统计表落盘为 CSV，同时用 pyecharts 生成可离线打开的 `看板.html`
- **本地文档文本分析**：把 docx / txt / md / csv / 文字型 PDF 抽取为「一条文本一行」的表，
  算六项语料指标（总文本条数、总字数、总词数、去重词汇量、平均句子长度、缺失文本数量），
  并出图：全语料总览 3 张 + **每份文档各 5 张**（词频饼图、词频 Top20、句长分布、平均句长对比、词数 vs 去重词汇量）
- **桌面端**：URL 抓取（可随时停止）、一键采集、生成报告、筛选看板（按日期/数据源/TopN 重算，可选表看图、另存 CSV 或 Excel）、文本分析（选目录 → 抽取 → 自动出图，六个指标卡 + 总览/分文档两个子页）、数据目录浏览与预览、运行日志、数据体检、使用说明；托盘常驻，关闭窗口不退出
- **自动化**：Windows 计划任务（每日定时采集并生成报告）与开机自启脚本
- **打包**：Nuitka 编译（推荐，启动更快、误报更少）或 PyInstaller 打包为 onedir 免安装目录
- **安装包**：Inno Setup 脚本（`tools\installer\CrawlerStudio.iss`），免管理员安装，含开始菜单与卸载入口

## 技术栈

Python 3.13 · requests · BeautifulSoup4 · lxml · pandas · pyecharts · PySide6
jieba · python-docx · pypdf（文本分析）· Nuitka / PyInstaller / Inno Setup（打包）

## 环境要求与安装

- Windows 10 / 11，Python 3.13
- 依赖列表见 `requirements.txt`

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 使用方法

### 桌面端

```powershell
.\.venv\Scripts\python.exe main.py
```

「筛选看板」页是软件里看图表的地方：选好日期 / 数据源 / Top N，点「生成视图」，
几秒后分三个子页看 —— 总览看板、单源指标（选表看图 + 另存）、跨源对比。
采集或生成报告跑完之后，它也会自动重算一遍并切过去。

「文本分析」页用来分析本地文档：选一个放文档的目录 → 点「① 开始抽取」（抽完会自动接着生成图表），
然后在「全语料总览」和「分文档图（每份 5 张）」两个子页看结果；指标卡显示六项语料指标，
缺失数不为 0 时会标红。想打开报告目录点「打开报告目录」。

第二行的「■ 停止」用来中止正在进行的抓取或采集（已抓到的数据保留）；
点右上角 × 只是收进托盘，真正退出用托盘右键菜单。

### 命令行

```powershell
.\.venv\Scripts\python.exe run_daily.py                # 采集全部站点，完成后自动生成报告
.\.venv\Scripts\python.exe run_daily.py baidu douban   # 只采集指定站点
.\.venv\Scripts\python.exe -m analysis.report          # 只生成报告
.\.venv\Scripts\python.exe web_crawler.py              # 通用网页采集（命令行交互）
.\.venv\Scripts\python.exe -m extract.documents 目录   # 抽取本地文档（docx/txt/md/csv/文字型 PDF）
.\.venv\Scripts\python.exe -m analysis.text_report     # 语料六项指标 + 图表（总览 3 张 + 每份文档 5 张）
```

> `-m` 形式需在项目根目录执行，否则会因找不到包而报 `ModuleNotFoundError`。

### 自检命令

```powershell
.\.venv\Scripts\python.exe -m utils.housekeeping   # 清理空目录与过期采集锁
.\.venv\Scripts\python.exe -m warehouse.boards     # 打印长表规模、各数据集行数与体检结果（需 data/ 里已有数据）
.\.venv\Scripts\python.exe -m analysis.common      # 打印各数据集行数与频次表自检
```

### 计划任务与开机自启

打包出 exe 后，双击 `tools\` 下的脚本即可（会先打印配置清单并要求确认）：

| 脚本 | 说明 |
|---|---|
| `install_task.bat` | 安装计划任务：每天 10:00 / 15:00 / 19:00 采集并生成报告 |
| `run_task_now.bat` | 立即触发一次任务 |
| `task_status.bat` | 查看任务状态、上次运行时间与结果码 |
| `remove_task.bat` | 删除计划任务 |
| `install_autostart.bat` | 设置开机自启（快捷方式方式，静默启动到托盘） |
| `remove_autostart.bat` | 取消开机自启 |

### 打包（路线 A：Nuitka，推荐）

```powershell
tools\build_nuitka.bat          # 增量编译：改了几行代码时用，3~10 分钟
tools\build_nuitka_clean.bat    # 全量编译：首次、或改了编译参数，20~40 分钟
```

- 产物：`build_nuitka\main.dist\CrawlerStudio.exe`（连同同级资源约 640 MB）
- 需要 C 编译器：装了 Visual Studio 的 C++ 工具链即可（Nuitka 自动用 MSVC）；没有就加 `--mingw64` 让它自动下载
- 编译版与"直接跑"有三处环境差异，代码里已经统一处理：
  1. `sys.frozen` 只有 PyInstaller 会设 → 一律用 `utils/paths.is_frozen()` 判断
  2. Nuitka 的 `sys.executable` 指向不存在的 `python.exe` → 起子进程一律用 `utils/paths.self_exe()`
  3. Nuitka 的模块加载器不支持 `runpy` → `--task` 机制改为「导入模块 + 调 `main()`」，
     因此**能被 `--task` 跑的模块都要有 `main() -> int`**（`run_daily.py` 是顶层脚本，单独列在 `TOP_LEVEL_MODULES`）
- 排障：`CrawlerStudio.exe --probe` 会打印 `sys.frozen` / `__compiled__` / `self_exe()` / `PYTHON` 等判定结果

### 打包（路线 B：PyInstaller）

打包参数都写在 `CrawlerStudio.spec` 里（入口、图标、版本信息、`hiddenimports`、
pyecharts 模板，以及排除用不到的模块与 Qt 调试资源），项目根目录一条命令即可：

```powershell
.venv\Scripts\pyinstaller.exe --noconfirm --clean CrawlerStudio.spec

robocopy charts\assets dist\CrawlerStudio\charts\assets echarts.min.js
robocopy assets       dist\CrawlerStudio\assets       app.ico
```

- 产物 `dist\CrawlerStudio\`（exe + `_internal\`），约 555 MB；整个文件夹拷到别的机器即可运行，**不需要装 Python**
- 打包会重建 `dist\CrawlerStudio\`，所以后面两条 `robocopy` 每次都要重跑（程序以 exe 所在目录为数据根目录）
- `hiddenimports` 里列的是以字符串形式调用的模块（`run_daily`、`analysis.report`、`analysis.text_report`、`extract.documents` 及 5 个站点脚本），静态分析识别不到，必须显式声明
- 用 `--onedir` 而非 `--onefile`，避免运行期自解压

### 制作安装包（Inno Setup）

```powershell
# 用 Inno Setup Compiler 打开脚本后按 F9，或命令行：
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" tools\installer\CrawlerStudio.iss
```

- 脚本：`tools\installer\CrawlerStudio.iss`；产物输出到项目根的 `installer\`
- 免管理员安装（`PrivilegesRequired=lowest`，装到 `%LOCALAPPDATA%\Programs`），安装包与程序都带图标
- 脚本里排除了 `data\ reports\ logs\ views\`：不会把开发时的数据装给别人
- 程序运行期数据保存在 exe 同级目录，**卸载时会保留**

## 项目结构

```
crawler/
├── main.py                   桌面端入口（PySide6）
├── gui/                      桌面端组件
│   ├── worker.py             外部脚本调用与输出转发（QProcess）
│   ├── url_crawler.py        URL 采集线程
│   └── help_text.py          界面内「使用说明」文案
├── run_daily.py              采集入口：依次运行各站点脚本，随后生成报告
├── baidu_api.py              百度热搜榜
├── bilibili_rank.py          B 站全站日榜
├── juejin_api.py             掘金热榜
├── toutiao_api.py            今日头条热榜
├── douban_boards.py          豆瓣电影/读书 Top250、豆列
├── web_crawler.py            通用网页采集
├── CrawlerStudio.spec        打包配置（图标、版本、hiddenimports、排除规则）
├── extract/                  抽取层：本地文档 → 「一条文本一行」的表
│   ├── common.py             编码探测、文本清洗、字数统计
│   ├── txtfile.py docxfile.py pdf_file.py csv_file.py   四类文件的抽取器
│   └── documents.py          总入口：遍历目录 → 抽取 → 落 data/documents/
├── parsers/                  解析层：原始内容 → 行数据
├── warehouse/                读取层：快照 CSV → 统一长表（含体检）
├── analysis/                 分析层：统计计算
│   ├── common.py             通用函数
│   ├── douban.py baidu.py bilibili.py hot.py    单源分析
│   ├── cross.py              跨源分析
│   ├── report.py             报告入口：计算 → 打印 → 落盘（归档到 reports/）
│   ├── live_view.py          筛选看板入口：按条件过滤 → 重算统计 → 出图
│   ├── text.py               语料指标：六项统计 + 词频 + 句长分布（纯函数）
│   └── text_report.py        文本分析报告入口：指标 + 每份文档的统计表 → 图表
├── charts/basic.py           图表层：统计表 → pyecharts 图
├── utils/                    工具层：路径、会话与 robots、列约定、存档、日志、清理、子进程输出编码
├── tools/                    计划任务、开机自启、图标生成、打包与安装包脚本
│   ├── build_nuitka.bat      增量编译（Nuitka）
│   ├── build_nuitka_clean.bat 全量编译（Nuitka）
│   └── installer/CrawlerStudio.iss   安装包脚本（Inno Setup）
├── assets/                   程序图标
├── data/                     数据目录
├── reports/                  报告产物（归档留档，里面也有 看板.html）
├── views/                    筛选看板生成的图表与统计表（点「生成视图」时产生）
└── logs/                     运行日志
```

## 数据组织

```
data/<域名>/<快照时间>/
├── raw/          原始响应，不做任何修改
└── *.csv         解析后的结构化数据

data/documents/<快照时间>/    本地文档抽取结果（extracted.csv + 文件清单）

reports/<时间>/   统计 CSV + 看板.html + 说明文件 + 离线图表库（归档留档）
views/            筛选看板生成的图表与统计表（点「生成视图」时产生）
logs/             运行日志与采集锁
```

`data/` 不存在或为空时，程序启动会自动创建，并放一个 `example/说明.txt` 占位。

命名约定：文件名不带层级词与域名，层级由目录表达；同一数据集的原始文件与成品文件同名，仅扩展名不同
（如 `raw/hot.json` ↔ `hot.csv`）。字段约定见 `utils/schema.py`，长表结构见 `warehouse/boards.py`。

## 采集站点

| 脚本 | 数据源 | 产出 |
|---|---|---|
| `baidu_api.py` | 百度热搜榜接口 | `data/top.baidu.com/<时间>/board.csv` |
| `bilibili_rank.py` | B 站全站日榜（经 tophub.today） | `data/tophub.today/<时间>/bilibili.csv` |
| `douban_boards.py` | 豆瓣电影 Top250、读书 Top250、豆列 | `data/movie.douban.com`、`book.douban.com`、`www.douban.com` 各自的快照 |
| `juejin_api.py` | 稀土掘金热榜接口 | `data/api.juejin.cn/<时间>/hot.csv` |
| `toutiao_api.py` | 今日头条热榜接口 | `data/www.toutiao.com/<时间>/hot.csv` |
| `web_crawler.py` | 用户输入的目标站点 | `data/<域名>/<时间>/pages.csv` |

## 合规声明

本项目仅用于个人学习与技术练习。抓取过程低频、礼貌，遵循目标站点的 `robots.txt` 与使用条款，
不抓取非公开数据与个人信息，不用于任何商业用途。
文本分析只处理你自己选择的本地目录，程序不会主动扫描硬盘。

## 相关文档

| 文件 | 内容 |
|---|---|
| `sites.md` | 站点清单、robots 实测记录、字段与接入说明 |
| 界面内「使用说明」页 | 面向使用者的常见问题解答 |
