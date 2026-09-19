# crawler · 榜单采集与分析工具

一个把「多站点榜单采集 → 快照归档 → 统一读取 → 统计分析 → 图表看板」串起来的 Python 项目，
带 PySide6 桌面端，可打包为免安装的绿色版程序。

> 当前版本 **0.1.1** ｜ 打包配置：`CrawlerStudio.spec`

## 功能

- **采集**
  - 站点采集：百度热搜、B 站全站日榜、豆瓣电影/读书 Top250 与豆列、掘金热榜、今日头条热榜
  - 通用网页采集：输入任意网址，抓取主页并可继续抓站内子页，正文清洗后存档
  - 请求前检查目标站点 `robots.txt`，不允许的域名直接跳过
- **归档**：原始响应（JSON / HTML）与解析结果（CSV）按「域名 / 时间」分快照存放，解析规则变更后可离线重跑
- **读取层**：将分散在各快照的 CSV 合并为一张统一长表，补充数据集、来源、时间等派生列
- **分析**：单源统计（评分分布、年代分布、票数与播放量增长、作者上榜次数、标签构成等）+ 跨源比对（榜单覆盖、同日 Top、同话题、榜单翻新速度）
- **图表与报告**：统计表落盘为 CSV，同时用 pyecharts 生成可离线打开的 `看板.html`
- **桌面端**：URL 抓取（可随时停止）、一键采集、生成报告、筛选看板（按日期/数据源/TopN 重算，可选表看图、另存 CSV 或 Excel）、数据目录浏览与预览、运行日志、数据体检、使用说明；托盘常驻，关闭窗口不退出
- **自动化**：Windows 计划任务（每日定时采集并生成报告）与开机自启脚本
- **打包**：支持 PyInstaller 打包为 onedir 免安装目录

## 技术栈

Python 3.13 · requests · BeautifulSoup4 · lxml · pandas · pyecharts · PySide6 · PyInstaller

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

第二行的「■ 停止」用来中止正在进行的抓取或采集（已抓到的数据保留）；
点右上角 × 只是收进托盘，真正退出用托盘右键菜单。

### 命令行

```powershell
.\.venv\Scripts\python.exe run_daily.py                # 采集全部站点，完成后自动生成报告
.\.venv\Scripts\python.exe run_daily.py baidu douban   # 只采集指定站点
.\.venv\Scripts\python.exe -m analysis.report          # 只生成报告
.\.venv\Scripts\python.exe web_crawler.py              # 通用网页采集（命令行交互）
```

> `-m` 形式需在项目根目录执行，否则会因找不到包而报 `ModuleNotFoundError`。

### 自检命令

```powershell
.\.venv\Scripts\python.exe -m utils.housekeeping   # 清理空目录与过期采集锁
.\.venv\Scripts\python.exe -m warehouse.boards     # 打印长表规模、各数据集行数与体检结果
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

### 打包

打包参数都写在 `CrawlerStudio.spec` 里（入口、图标、版本信息、`hiddenimports`、
pyecharts 模板，以及排除用不到的模块与 Qt 调试资源），所以在项目根目录执行一条命令就够：

```powershell
.venv\Scripts\pyinstaller.exe --noconfirm --clean CrawlerStudio.spec

robocopy charts\assets dist\CrawlerStudio\charts\assets echarts.min.js
robocopy assets       dist\CrawlerStudio\assets       app.ico
robocopy data         dist\CrawlerStudio\data         /E
robocopy reports      dist\CrawlerStudio\reports      /E
```

说明：

- 产物是 `dist\CrawlerStudio\`（exe + `_internal\`），约 555 MB；整个文件夹拷到别的机器即可运行，**不需要装 Python**
- 打包会重建 `dist\CrawlerStudio\`，所以后面四条 `robocopy` 每次都要重跑：把图表库、图标、数据、报告放到 exe 同级目录（程序以 exe 所在目录为数据根目录）
- `hiddenimports` 里列的是以字符串形式调用的模块（`run_daily`、`analysis.report` 及 5 个站点脚本），PyInstaller 静态分析识别不到，必须显式声明
- 用 `--onedir` 而非 `--onefile`，避免运行期自解压，启动更快
- 想调整体积：改 `CrawlerStudio.spec` 里的 `EXCLUDES` 与 `keep_data()`

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
├── parsers/                  解析层：原始内容 → 行数据
├── warehouse/                读取层：快照 CSV → 统一长表（含体检）
├── analysis/                 分析层：统计计算
│   ├── common.py             通用函数
│   ├── douban.py baidu.py bilibili.py hot.py    单源分析
│   ├── cross.py              跨源分析
│   ├── report.py             报告入口：计算 → 打印 → 落盘（归档到 reports/）
│   └── live_view.py          筛选看板入口：按条件过滤 → 重算统计 → 出图
├── charts/basic.py           图表层：统计表 → pyecharts 图
├── utils/                    工具层：路径、会话与 robots、列约定、存档、日志、清理、子进程输出编码
├── tools/                    计划任务、开机自启、图标生成脚本
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

## 相关文档

| 文件 | 内容 |
|---|---|
| `sites.md` | 站点清单、robots 实测记录、字段与接入说明 |
| 界面内「使用说明」页 | 面向使用者的常见问题解答 |
