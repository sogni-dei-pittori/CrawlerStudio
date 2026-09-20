"""桌面端入口：URL 采集 / 站点采集 / 数据概况 / 资源管理 / 筛选看板。

跑法：python main.py （在项目根目录）
"""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QFileDialog,
                               QFileSystemModel, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
                               QSplitter, QStackedWidget, QStyle, QSystemTrayIcon, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QTreeView, QVBoxLayout,
                               QWidget)
from PySide6.QtWebEngineWidgets import QWebEngineView

from analysis.live_view import DATASET_LABELS  # 筛选看板的数据源清单（只此一份）
from gui.help_text import HELP_HTML
from gui.url_crawler import UrlCrawler
from gui.worker import ScriptRunner
from utils.housekeeping import clean_empty_dirs, clean_stale_lock, ensure_data_root
from utils.paths import BASE_DIR  # ★ 打包后自动指向 exe 所在目录
from warehouse import audit
from web_crawler import check_url

TOP_LEVEL_MODULES = {"run_daily"}
FROZEN = getattr(sys, "frozen", False)  # ★ 打包成 exe 后 PyInstaller 会设这个属性
PYTHON = sys.executable if FROZEN else str(BASE_DIR / ".venv" / "Scripts" / "python.exe")
DATA_DIR = BASE_DIR / "data"
PREVIEW_ROWS = 200  # 资源管理里预览 CSV 的前多少行
TABLE_PREVIEW_ROWS = 500  # 筛选看板里预览统计表的前多少行


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("爬虫项目 · 采集与分析")
        self.resize(1100, 760)
        self.setWindowIcon(self.app_icon())  # ★ 窗口/任务栏图标（assets/app.ico）
        self._runners = []  # ★ 保活：别让 QProcess 被垃圾回收

        central = QWidget()
        layout = QVBoxLayout(central)

        # ---------- 第一行：URL 采集 ----------
        url_bar = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("输入网址，例如 https://www.example.com/")
        self.chk_subpages = QCheckBox("抓站内子页")
        self.spin_subpages = QSpinBox()
        self.spin_subpages.setRange(1, 200)
        self.spin_subpages.setValue(20)
        self.btn_url = QPushButton("开始抓取")
        url_bar.addWidget(QLabel("URL："))
        url_bar.addWidget(self.url_input, 1)
        url_bar.addWidget(self.chk_subpages)
        url_bar.addWidget(QLabel("上限"))
        url_bar.addWidget(self.spin_subpages)
        url_bar.addWidget(self.btn_url)
        layout.addLayout(url_bar)

        # ---------- 第二行：站点采集 / 报告 ----------
        bar = QHBoxLayout()
        self.btn_collect = QPushButton("开始采集（run_daily）")
        self.btn_report = QPushButton("生成报告（analysis.report）")
        self.btn_check = QPushButton("刷新数据概况")
        self.btn_stop = QPushButton("■ 停止")
        self.btn_stop.setEnabled(False)  # 没任务在跑时不让点
        for b in (self.btn_collect, self.btn_report, self.btn_check, self.btn_stop):
            bar.addWidget(b)
        bar.addStretch()
        layout.addLayout(bar)

        # ---------- 标签页 ----------
        self.tabs = QTabWidget()

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.tabs.addTab(self.log, "运行日志")

        self.prepare_data_dir()  # ★ data/ 得先存在：下面资源管理页拿它当根

        self.overview = QTableWidget()
        self.tabs.addTab(self.overview, "数据概况")

        self.tabs.addTab(self._build_explorer(), "资源管理")

        self.help = QTextBrowser()  # ★ 使用说明：纯本地文字，不联网
        self.help.setOpenExternalLinks(False)
        self.help.setHtml(HELP_HTML)
        self.tabs.addTab(self.help, "使用说明")

        self.tabs.addTab(self._build_filter_view(), "筛选看板")  # ★ 活的：按条件重算
        self.tabs.addTab(self._build_text_view(), "文本分析")  # ★ 本地文档：抽取 → 六指标 → 图表

        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        # ---------- 信号 ----------
        self.btn_url.clicked.connect(self.start_url_crawl)
        self.url_input.returnPressed.connect(self.start_url_crawl)  # 回车也能开始
        self.btn_collect.clicked.connect(lambda: self.run_module("run_daily"))
        self.btn_report.clicked.connect(lambda: self.run_module("analysis.report"))
        self.btn_check.clicked.connect(self.refresh_overview)
        self.btn_stop.clicked.connect(self.stop_tasks)

        self.startup_cleanup()  # ★ 启动时扫一次：空目录 + 过期锁
        self.log.appendPlainText(
            "[提示] 有疑问先看『使用说明』标签页：按「你会遇到什么」整理了常见问题和答案。")

        self._really_quit = False  # ★ 托盘：标记"这次是真退出"（区分点×收进托盘）
        self._tray_hinted = False  # 第一次收进托盘时提示一下，别只提示一次
        self._build_tray()

    # ==================== 启动清理 ====================
    def startup_cleanup(self) -> None:
        """删掉 data/ 里的空目录，顺手清过期的采集锁。

        只在启动时跑，删了什么写进日志；清理本身出问题也绝不影响界面启动。
        """
        try:
            gone = clean_empty_dirs()  # 默认只扫 data/，且不碰 10 分钟内的新目录
            if gone:
                self.log.appendPlainText(f"[清理] 删掉 {len(gone)} 个空目录：")
                for item in gone[:10]:  # 最多列 10 条，别把日志刷满
                    self.log.appendPlainText(f"    · {item}")
                if len(gone) > 10:
                    self.log.appendPlainText(f"    ……还有 {len(gone) - 10} 个未列出")
            else:
                self.log.appendPlainText("[清理] data/ 里没有可清理的空目录。")

            lock = clean_stale_lock()
            if lock:
                self.log.appendPlainText(f"[清理] 删掉过期的采集锁：{lock}")
        except Exception as exc:  # 清理失败也要能正常启动
            self.log.appendPlainText(f"[清理] 出错（已跳过）：{exc.__class__.__name__}: {exc}")

    # ==================== 数据目录准备 ====================
    def prepare_data_dir(self) -> None:
        """保证 data/ 存在；它还是空的话，建一个 example/ 占位（里面带说明文件）。

        为什么必须做：右边「资源管理」页用 QFileSystemModel，根目录不存在（或完全为空）时
        那一页看起来像卡死了 —— 什么都没有，点了也没反应。占位目录里放了个文件，
        所以它是"非空目录"，启动清理不会把它当垃圾删掉。
        """
        try:
            hint = ensure_data_root(DATA_DIR)
            if hint:
                self.log.appendPlainText(f"[提示] data/ 还是空的，先建了 {hint} 占位。")
                self.log.appendPlainText("       随便抓个网址、或者点「开始采集」，这里就有真数据了。")
        except Exception as exc:
            self.log.appendPlainText(f"[提示] 准备数据目录出错（已跳过）：{exc.__class__.__name__}: {exc}")

    # ==================== 资源管理页 ====================
    def _build_explorer(self) -> QSplitter:
        """左边 data/ 文件树，右边预览：CSV 显示表格，其它文本显示前 100 行。

        QFileSystemModel 会自己跟随磁盘变化 → 抓完/跑完报告不用手动刷新。
        """
        DATA_DIR.mkdir(parents=True, exist_ok=True)  # ★ 根目录不存在，这一页会像卡死
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(str(DATA_DIR))
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(str(DATA_DIR)))
        self.tree.setColumnWidth(0, 320)
        for col in (1, 2, 3):  # 只留文件名列，其它三列（大小/类型/时间）隐藏
            self.tree.hideColumn(col)
        self.tree.clicked.connect(self.on_tree_clicked)

        self.preview_table = QTableWidget()
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.preview_table)  # 下标 0：表格
        self.preview_stack.addWidget(self.preview_text)  # 下标 1：文本

        split = QSplitter()
        split.addWidget(self.tree)
        split.addWidget(self.preview_stack)
        split.setStretchFactor(1, 3)
        return split

    def on_tree_clicked(self, index) -> None:
        """点文件树里的文件 → 右边预览。"""
        path = Path(self.fs_model.filePath(index))
        if path.is_dir():
            return
        try:
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(path, encoding="utf-8-sig",
                                 keep_default_na=False, nrows=PREVIEW_ROWS)
                self._fill_table(df)
                self.preview_stack.setCurrentIndex(0)
                self.log.appendPlainText(
                    f"[资源] 预览 {path.name}（{len(df)} 行 × {len(df.columns)} 列）")
            else:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                self.preview_text.setPlainText("\n".join(lines[:100]))
                self.preview_stack.setCurrentIndex(1)
                self.log.appendPlainText(
                    f"[资源] 预览 {path.name}（{len(lines)} 行文本，显示前 100 行）")
        except Exception as exc:
            self.log.appendPlainText(f"[资源] 打不开 {path.name}：{exc.__class__.__name__}: {exc}")

    def _fill_table(self, df, table=None) -> None:
        """把 DataFrame 填进 QTableWidget（数据量小，直接重建最省事）。

        table 不传 = 「资源管理」里那张预览表（原来的行为）；
        筛选看板会传自己那张表进来。
        """
        table = table if table is not None else self.preview_table
        table.clear()
        table.setRowCount(len(df))
        table.setColumnCount(len(df.columns))
        table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r in range(len(df)):
            for c, col in enumerate(df.columns):
                table.setItem(r, c, QTableWidgetItem(str(df.iloc[r][col])[:200]))
        table.resizeColumnsToContents()

    # ==================== 筛选看板 ====================
    def _build_filter_view(self) -> QWidget:
        """筛选看板页：日期范围 + 数据源 + Top N，点一下重新算一张看板。

        这是软件里唯一的图表页（原来那个直接看 reports/<时间>/看板.html 的「看板」页已删）：
        每次点「生成视图」都按当前条件重新读长表、重算统计、重画图。
        归档报告照旧落在 reports/<时间>/ 下，用浏览器双击也能看，只是不再单独开页面。
        """
        page = QWidget()
        box = QVBoxLayout(page)

        row = QHBoxLayout()
        self.date_start = QDateEdit(QDate(2000, 1, 1))
        self.date_end = QDateEdit(QDate.currentDate())
        for widget in (self.date_start, self.date_end):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
        self.spin_top = QSpinBox()
        self.spin_top.setRange(5, 100)
        self.spin_top.setValue(15)
        self.btn_filter = QPushButton("生成视图")
        self.btn_filter.clicked.connect(self.generate_filter_view)
        row.addWidget(QLabel("日期："))
        row.addWidget(self.date_start)
        row.addWidget(QLabel("~"))
        row.addWidget(self.date_end)
        row.addSpacing(16)
        row.addWidget(QLabel("Top N："))
        row.addWidget(self.spin_top)
        row.addSpacing(16)
        row.addWidget(self.btn_filter)
        row.addStretch()
        box.addLayout(row)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("数据源："))
        self.chk_sources = {}
        for name, label in DATASET_LABELS.items():
            chk = QCheckBox(label)
            chk.setChecked(True)  # 默认全选（不筛就是全量）
            self.chk_sources[name] = chk
            src_row.addWidget(chk)
        src_row.addStretch()
        box.addLayout(src_row)

        # ---------- 指标卡：这次筛选下的四个数字 ----------
        self.metrics = {}
        metric_row = QHBoxLayout()
        for key in ("全量行数", "当前视图", "数据集", "快照数"):
            value = QLabel("—")
            value.setStyleSheet("font-size:16px; font-weight:bold;")
            caption = QLabel(key)
            caption.setStyleSheet("color:#777;")
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(value)
            cell.addWidget(caption)
            metric_row.addLayout(cell)
            metric_row.addSpacing(28)
            self.metrics[key] = value
        metric_row.addStretch()
        box.addLayout(metric_row)

        # ---------- 子页：总览（原来的多图页） + 单源指标（像 app.py 那样选表看）----------
        self.filter_tabs = QTabWidget()
        self.filter_view = QWebEngineView()  # 总览用的内嵌浏览器
        self.filter_tabs.addTab(self.filter_view, "总览看板")
        self.filter_tabs.addTab(self._build_single_page(), "单源指标")
        self.filter_tabs.addTab(self._build_cross_page(), "跨源对比")
        box.addWidget(self.filter_tabs, 1)  # ★ 多出来的高度给子页，别让上面几行吃掉

        self.filter_page = page  # ★ 切标签页要用它（不能直接拿里面的 web view）
        return page

    def _build_single_page(self) -> QWidget:
        """「单源指标」子页：选一张统计表 → 看它的图、看它的数据、想留就另存。

        这就是 app.py 里"单源指标"那一页的效果：一个下拉选表，图和表都跟着换。
        显示用的是生成时落盘的文件（views/图表/<表名>.html、views/表/<表名>.csv），
        所以切换表是瞬间的，不用重新计算。
        """
        page = QWidget()
        box = QVBoxLayout(page)

        top = QHBoxLayout()
        self.combo_table = QComboBox()
        self.combo_table.setMinimumWidth(240)
        self.combo_table.currentIndexChanged.connect(self.on_filter_table_changed)
        self.btn_save_table = QPushButton("另存这张表…")
        self.btn_save_table.clicked.connect(self.save_filter_table)
        self.lbl_table = QLabel("（先点上面的「生成视图」）")
        self.lbl_table.setStyleSheet("color:#777;")
        top.addWidget(QLabel("统计表："))
        top.addWidget(self.combo_table)
        top.addWidget(self.btn_save_table)
        top.addSpacing(16)
        top.addWidget(self.lbl_table)
        top.addStretch()
        box.addLayout(top)

        # 图在上、表在下；多出来的高度给"下面那张表"（图那边够放下就行）
        split = QSplitter()
        split.setOrientation(Qt.Orientation.Vertical)
        self.table_chart = QWebEngineView()  # 这张表对应的图（表里没图就显示一句说明）
        self.filter_table = QTableWidget()  # 这张表的数据
        split.addWidget(self.table_chart)
        split.addWidget(self.filter_table)
        split.setSizes([420, 380])  # 初始各占多少
        split.setStretchFactor(0, 0)  # 图上：不跟着长
        split.setStretchFactor(1, 1)  # 表下：窗口变大时它先长
        box.addWidget(split, 1)
        return page

    def _build_cross_page(self) -> QWidget:
        """「跨源对比」子页：两张跨源图 + 同日各源 Top N 表（对齐 app.py 那一页）。

        左边加载生成好的 跨源对比.html（翻新速度折线 + 同话题名次对比，一张页面两张图），
        右边是"同日各源 Top N"的数据表；上面那句说明和 app.py 里的口径一致。
        """
        page = QWidget()
        box = QVBoxLayout(page)

        self.lbl_cross = QLabel("（先点上面的「生成视图」）")
        self.lbl_cross.setStyleSheet("color:#777;")
        box.addWidget(self.lbl_cross)

        split = QSplitter()
        self.cross_view = QWebEngineView()
        self.cross_table = QTableWidget()
        split.addWidget(self.cross_view)
        split.addWidget(self.cross_table)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        box.addWidget(split, 1)  # ★ 同上：高度都给内容区
        return page

    def generate_filter_view(self) -> None:
        """按当前条件生成看板：丢到子进程里算，界面不会卡。"""
        picked = [name for name, chk in self.chk_sources.items() if chk.isChecked()]
        if not picked:
            self.log.appendPlainText("[提示] 至少要勾一个数据源。")
            return
        args = [
            "--start", self.date_start.date().toString("yyyy-MM-dd"),
            "--end", self.date_end.date().toString("yyyy-MM-dd"),
            "--datasets", ",".join(picked),
            "--top", str(self.spin_top.value()),
        ]
        self.run_module("analysis.live_view", args)

    def load_filter_view(self) -> None:
        """生成完之后：读清单 → 填指标卡和表下拉 → 切到「筛选看板」页。"""
        manifest_path = BASE_DIR / "views" / "_清单.json"
        if not manifest_path.is_file():
            self.log.appendPlainText(f"[提示] 没找到 {manifest_path}，生成可能失败了。")
            return
        try:
            self.filter_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.log.appendPlainText(f"[提示] 清单读不出来：{exc.__class__.__name__}: {exc}")
            return

        for key, label in self.metrics.items():  # ① 指标卡
            label.setText(str(self.filter_manifest["指标"].get(key, "—")))

        self.combo_table.blockSignals(True)  # ② 表下拉（填的时候别触发一堆刷新）
        self.combo_table.clear()
        for item in self.filter_manifest["表"]:
            self.combo_table.addItem(f"{item['名字']}（{item['行数']} 行）", item)
        self.combo_table.blockSignals(False)

        html = BASE_DIR / "views" / "筛选看板.html"  # ③ 总览页
        if html.is_file():
            self.filter_view.load(QUrl.fromLocalFile(str(html)))

        cross = self.filter_manifest.get("跨源对比") or {}  # ③' 跨源对比子页
        cross_html = BASE_DIR / "views" / cross.get("页面", "跨源对比.html")
        if cross_html.is_file():
            self.cross_view.load(QUrl.fromLocalFile(str(cross_html)))
        same_day = cross.get("同日TopN") or {}
        if same_day.get("csv"):
            cross_csv = BASE_DIR / "views" / same_day["csv"]
            if cross_csv.is_file():
                df = pd.read_csv(cross_csv, encoding="utf-8-sig", keep_default_na=False,
                                 nrows=TABLE_PREVIEW_ROWS)
                self._fill_table(df, self.cross_table)
        charts_n = cross.get("有几张图", 0)
        self.lbl_cross.setText(
            f"跨源对比：{charts_n} 张图"
            f"　｜　同日各源 Top{same_day.get('n', '?')} 共 {same_day.get('行数', 0)} 行"
            "　（翻新率越低=翻新越快；名次越小越好）"
            + ("" if charts_n >= 2 else
               "　※ 翻新速度至少要两天的数据；同话题对比要两个源在同一天出现相近的标题"))

        self.tabs.setCurrentWidget(self.filter_page)
        self.filter_tabs.setCurrentIndex(0)

        # ④ 刷一次当前表。
        #   ★ 坑：addItem 之后 currentIndex 已经自动是 0，再 setCurrentIndex(0) 不算"变化"，
        #     Qt 不会发 currentIndexChanged —— 所以这里必须显式调一次，别指望信号。
        self.on_filter_table_changed()

        metrics = self.filter_manifest["指标"]
        self.log.appendPlainText(
            f"[筛选看板] 已加载（当前视图 {metrics.get('当前视图', '?')} 行，"
            f"{len(self.filter_manifest['表'])} 张统计表，"
            f"日期 {metrics.get('日期范围', '?')}）")

    def on_filter_table_changed(self) -> None:
        """换一张表：图和数据一起换（直接读生成时落盘的文件，不用重算）。"""
        item = self.combo_table.currentData()
        if not item:
            return
        views = BASE_DIR / "views"
        csv_path = views / item["csv"]
        if csv_path.is_file():
            df = pd.read_csv(csv_path, encoding="utf-8-sig", keep_default_na=False,
                             nrows=TABLE_PREVIEW_ROWS)
            self._fill_table(df, self.filter_table)  # ★ 填筛选看板自己那张表
            more = "" if item["行数"] <= TABLE_PREVIEW_ROWS else f"，只显示前 {TABLE_PREVIEW_ROWS} 行"
            self.lbl_table.setText(f"{item['行数']} 行 × {item['列数']} 列{more}"
                                   f"　（views/{item['csv']}）")
        chart_rel = item.get("图")
        if chart_rel and (views / chart_rel).is_file():
            self.table_chart.load(QUrl.fromLocalFile(str(views / chart_rel)))
        else:
            self.table_chart.setHtml(
                "<html><body style=\"font-family:'Microsoft YaHei',sans-serif;"
                "padding:24px;color:#666\"><h3>这张表没有对应的图</h3>"
                "<p>它更适合直接看下面的数据表（也可能是被当前筛选筛空了）。</p>"
                "</body></html>")

    def save_filter_table(self) -> None:
        """另存当前这张表：CSV 直接复制，xlsx 用 pandas 转一下。"""
        item = self.combo_table.currentData()
        if not item:
            self.log.appendPlainText("[提示] 先生成视图，再另存。")
            return
        src = BASE_DIR / "views" / item["csv"]
        if not src.is_file():
            self.log.appendPlainText(f"[提示] 文件不在：{src}")
            return
        default = str(Path.home() / "Desktop" / f"{item['名字']}.csv")
        target, _ = QFileDialog.getSaveFileName(self, "另存统计表", default,
                                                "CSV 表格（*.csv）;;Excel 工作簿（*.xlsx）")
        if not target:
            return
        try:
            if target.lower().endswith(".xlsx"):
                pd.read_csv(src, encoding="utf-8-sig").to_excel(target, index=False)
            else:
                shutil.copy(src, target)
        except Exception as exc:
            self.log.appendPlainText(f"[提示] 另存失败：{exc.__class__.__name__}: {exc}")
            return
        self.log.appendPlainText(f"[另存] {item['名字']} → {target}")

    # ==================== URL 采集 ====================
    # ==================== 文本分析（本地文档） ====================
    @staticmethod
    def _fmt_metric(raw) -> str:
        """指标卡的显示格式：整数加千分位、不带 .0；不是数字就原样返回（如 '—'）。"""
        try:
            num = float(raw)
        except (TypeError, ValueError):
            return str(raw)
        if num.is_integer():
            return f"{int(num):,}"
        return f"{num:,.2f}".rstrip("0").rstrip(".")

    def _build_text_view(self) -> QWidget:
        """文本分析页：选一个本地目录 → ① 抽取 → ② 出图表。

        和「筛选看板」的分工：那一页吃抓来的网页榜单数据，这一页吃本地文件
        （docx / txt / md / csv / 文字型 pdf）。两页的用法是一样的：改条件 → 重算 → 出图。
        """
        page = QWidget()
        box = QVBoxLayout(page)

        # ---- 第 1 行：语料目录 + 两个动作按钮 ----
        row = QHBoxLayout()
        self.txt_dir = QLineEdit(self._default_corpus_dir())
        self.txt_dir.setPlaceholderText("放文档的目录（docx / txt / md / csv / 文字型 pdf）")
        self.btn_txt_pick = QPushButton("选择目录…")
        self.btn_txt_extract = QPushButton("① 开始抽取")
        self.btn_txt_report = QPushButton("② 生成图表")
        self.btn_txt_open = QPushButton("打开报告目录")
        row.addWidget(QLabel("语料目录："))
        row.addWidget(self.txt_dir, 1)
        row.addWidget(self.btn_txt_pick)
        row.addSpacing(12)
        row.addWidget(self.btn_txt_extract)
        row.addWidget(self.btn_txt_report)
        row.addWidget(self.btn_txt_open)
        box.addLayout(row)

        # ---- 第 2 行：六个指标卡（跑完 ② 才填数）----
        self.txt_metrics = {}
        metric_row = QHBoxLayout()
        for key in ("语料文件", "文本条数", "总字数", "总词数", "去重词汇量", "缺失文本"):
            value = QLabel("—")
            value.setStyleSheet("font-size:16px; font-weight:bold;")
            caption = QLabel(key)
            caption.setStyleSheet("color:#777;")
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(value)
            cell.addWidget(caption)
            metric_row.addLayout(cell)
            metric_row.addSpacing(28)
            self.txt_metrics[key] = value
        metric_row.addStretch()
        box.addLayout(metric_row)

        # ---- 第 3 行：两个子页（内嵌浏览器看生成好的 HTML）----
        self.txt_tabs = QTabWidget()
        self.txt_overview = QWebEngineView()
        self.txt_perdoc = QWebEngineView()
        self.txt_tabs.addTab(self.txt_overview, "全语料总览")
        self.txt_tabs.addTab(self.txt_perdoc, "分文档图（每份 5 张）")
        for view in (self.txt_overview, self.txt_perdoc):
            view.setHtml(self._text_placeholder(
                "还没有生成图表",
                "选好「语料目录」→ 点「① 开始抽取」→ 抽完会自动出图表。"))
        box.addWidget(self.txt_tabs, 1)      # ★ 多出来的高度给子页，别让上面几行吃掉

        self.btn_txt_pick.clicked.connect(self.pick_corpus_dir)
        self.btn_txt_extract.clicked.connect(self.start_text_extract)
        self.btn_txt_report.clicked.connect(lambda: self.run_module("analysis.text_report"))
        self.btn_txt_open.clicked.connect(self.open_text_report_dir)

        # ★ 启动就把最近一批报告显示出来（没有就保持占位页，不会报错）。
        #   否则报告明明已经生成过、界面却显示「还没有生成图表」，很让人困惑。
        self.load_text_report()
        return page

    @staticmethod
    def _default_corpus_dir() -> str:
        """默认语料目录：桌面的「语料」文件夹；没有就用桌面本身。"""
        desktop = Path.home() / "Desktop"
        corpus = desktop / "语料"
        return str(corpus if corpus.is_dir() else desktop)

    @staticmethod
    def _text_placeholder(title: str, message: str) -> str:
        """占位页：没生成报告时别给一片空白（和筛选看板的提示页一个套路）。"""
        return ("<html><body style=\"font-family:'Microsoft YaHei',sans-serif;height:100%;"
                "display:flex;align-items:center;justify-content:center;\">"
                f"<div style='text-align:center;color:#777;'>"
                f"<h3 style='color:#444;margin:0 0 8px'>{title}</h3>"
                f"<p style='font-size:14px;margin:0'>{message}</p></div></body></html>")

    def pick_corpus_dir(self) -> None:
        """选语料目录（从上次选的位置打开，省得每次翻到桌面）。"""
        chosen = QFileDialog.getExistingDirectory(
            self, "选择放文档的目录", self.txt_dir.text().strip() or str(Path.home()))
        if chosen:
            self.txt_dir.setText(chosen)

    def start_text_extract(self) -> None:
        """① 抽取：把目录里的文档变成「一条文本一行」的表（落在 data/documents/ 下）。"""
        folder = self.txt_dir.text().strip().strip('"')
        if not folder:
            self.log.appendPlainText("[提示] 先选一个语料目录（放 docx / txt / md / csv / 文字型 pdf 的文件夹）。")
            return
        if not Path(folder).is_dir():
            self.log.appendPlainText(f"[提示] 目录不存在：{folder}")
            return
        self.run_module("extract.documents", [folder])   # 抽完会自动接着出图表

    def latest_text_report_dir(self):
        """reports/ 里最近一批**文本分析**报告。

        用「语料_总体指标.csv」认定：网络榜单那批报告里没有这个文件，
        所以不会把「筛选看板」的批次误认成文本报告。
        """
        root = BASE_DIR / "reports"
        if not root.is_dir():
            return None
        dirs = [p for p in root.iterdir()
                if p.is_dir() and (p / "语料_总体指标.csv").is_file()]
        return max(dirs, key=lambda p: p.name) if dirs else None

    def open_text_report_dir(self) -> None:
        """用资源管理器打开最近一批文本报告目录。"""
        latest = self.latest_text_report_dir()
        if latest is None:
            self.log.appendPlainText("[提示] 还没有文本分析报告，先点「② 生成图表」。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(latest)))

    def load_text_report(self) -> None:
        """把最近一批文本报告的六个指标和两个 HTML 装进界面。"""
        latest = self.latest_text_report_dir()
        if latest is None:
            return
        try:
            # ★ dtype=str：不加的话"值"列混合整数和小数会被读成 float，
            #   指标卡就显示成 71725.0（难看），而且缺失数解析会报 ValueError
            metrics = pd.read_csv(latest / "语料_总体指标.csv",
                                   keep_default_na=False, dtype=str)
            values = {str(k): str(v) for k, v in zip(metrics["指标"], metrics["值"])}
            per_doc = pd.read_csv(latest / "语料_每份文件.csv", keep_default_na=False)
        except Exception as exc:                   # 报告被删/被占用都别让界面崩
            self.log.appendPlainText(f"[提示] 读报告失败：{type(exc).__name__}: {exc}")
            return

        shown = {
            "语料文件": len(per_doc),
            "文本条数": values.get("总文本条数", "—"),
            "总字数": values.get("总字数", "—"),
            "总词数": values.get("总词数", "—"),
            "去重词汇量": values.get("去重词汇量", "—"),
            "缺失文本": values.get("缺失文本数量", "—"),
        }
        for key, label in self.txt_metrics.items():
            label.setText(self._fmt_metric(shown.get(key, "—")))
        # 有缺失就标红：这是"数据质量"信号，别让它混在一堆灰字里
        try:
            missing = int(float(values.get("缺失文本数量", 0) or 0))   # 兜底：万一写成 0.0 也不炸
        except (TypeError, ValueError):
            missing = 0
        self.txt_metrics["缺失文本"].setStyleSheet(
            "font-size:16px; font-weight:bold;" + (" color:#c0392b;" if missing else ""))

        for name, view in (("文本分析.html", self.txt_overview),
                           ("文本分析_分文档.html", self.txt_perdoc)):
            path = latest / name
            if path.is_file():
                view.load(QUrl.fromLocalFile(str(path)))
            else:
                view.setHtml(self._text_placeholder("这一页没生成", f"报告目录里没有 {name}。"))
        self.txt_tabs.setCurrentIndex(0)
        self.log.appendPlainText(f"[文本分析] 已加载：{latest}")

    def start_url_crawl(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            self.log.appendPlainText("[提示] 先输入网址。")
            return
        ok, result = check_url(url)  # ★ 先做域名校验，不合格直接退出本次爬取
        if not ok:
            self.log.appendPlainText(f"[提示] {result}，本次爬取已取消。")
            return
        url = result  # 后面统一用补全过的地址
        if getattr(self, "crawler", None) is not None and self.crawler.isRunning():
            self.log.appendPlainText("[提示] 上一次抓取还在进行，请等它结束。")
            return

        subpages = self.chk_subpages.isChecked()
        self.btn_url.setEnabled(False)
        self.log.appendPlainText(
            f"\n$ 抓取 {url}（子页：{'是' if subpages else '否'}，上限 {self.spin_subpages.value()} 页）")

        self.crawler = UrlCrawler(url, subpages, self.spin_subpages.value())
        self.crawler.progress.connect(self.log.appendPlainText)
        self.crawler.page_done.connect(self.on_page_done)
        self.crawler.done.connect(self.on_crawl_done)
        self.crawler.stopped.connect(self.on_crawl_stopped)
        self.crawler.failed.connect(self.on_crawl_failed)
        self.crawler.start()
        self._refresh_stop_button()

    def on_page_done(self, row: dict) -> None:
        """每抓到一页，在日志里补一行标题（进度文本之外多一层确认）。"""
        self.log.appendPlainText(f"    · {str(row.get('title') or '')[:40]}")

    def on_crawl_done(self, csv_path: str, pages: int) -> None:
        self.log.appendPlainText(f"[完成] 共 {pages} 页 → {csv_path}")
        self.log.appendPlainText("[提示] 到『资源管理』标签页里找到这个 pages.csv 就能看内容。")
        self.btn_url.setEnabled(True)
        self._refresh_stop_button()
        self.refresh_overview()

    def on_crawl_stopped(self, csv_path: str, pages: int) -> None:
        """用户点了停止：已经抓到的那几页都留着。"""
        self.log.appendPlainText(f"[已停止] 网页抓取停了，已抓到 {pages} 页 → {csv_path}")
        self.btn_url.setEnabled(True)
        self._refresh_stop_button()
        self.refresh_overview()

    def on_crawl_failed(self, reason: str) -> None:
        self.log.appendPlainText(f"[失败] {reason}")
        self.btn_url.setEnabled(True)
        self._refresh_stop_button()

    # ==================== 站点采集 / 报告 ====================
    def run_module(self, module: str, extra: list[str] | None = None) -> None:
        """跑项目里的模块：没打包用 `python -m 模块`，打包后用 `exe --task 模块`。

        两种写法效果一样，区别只在"谁来当解释器"。
        extra 是传给那个模块的参数（比如筛选看板的 --start/--end/--datasets/--top）。
        """
        self.last_module = module  # ★ 记住这次跑的是谁，跑完才知道该刷哪一页
        self.run_script("--task" if FROZEN else "-m", [module, *(extra or [])])

    def run_script(self, script: str, args: list[str] | None = None) -> None:
        # ★ 上一次还在跑就拒绝：否则旧 runner 会被回收，QProcess 被销毁 → 崩溃
        if getattr(self, "runner", None) is not None and self.runner.is_running():
            self.log.appendPlainText("[提示] 上一次任务还在运行，请等它结束。")
            return

        self.last_script = script
        self.log.appendPlainText(f"\n$ python {script} {' '.join(args or [])}")
        self.btn_collect.setEnabled(False)  # 跑的时候禁用按钮，防重复点
        self.btn_report.setEnabled(False)
        self.btn_txt_extract.setEnabled(False)
        self.btn_txt_report.setEnabled(False)

        self.runner = ScriptRunner(PYTHON, script, args, cwd=str(BASE_DIR))
        self._runners.append(self.runner)  # ★ 保活
        self.runner.output.connect(self.log.insertPlainText)
        self.runner.finished.connect(self.on_finished)
        self.runner.error.connect(self.on_error)
        self.runner.start()
        self._refresh_stop_button()

    def on_finished(self, code: int) -> None:
        stopped = getattr(self, "runner", None) is not None and self.runner.was_stopped()
        if stopped:
            self.log.appendPlainText("\n[已停止] 任务被你手动停掉了（已经产出的数据都留着）")
        else:
            self.log.appendPlainText(f"\n[进程结束] 退出码 = {code}" + ("（成功）" if code == 0 else "（失败）"))
        self.btn_collect.setEnabled(True)
        self.btn_report.setEnabled(True)
        self.btn_txt_extract.setEnabled(True)
        self.btn_txt_report.setEnabled(True)
        self._refresh_stop_button()
        if stopped or code != 0:
            return
        # 跑完自动刷新页面（按 last_module 分流）
        module = getattr(self, "last_module", "")
        if module == "analysis.live_view":
            self.load_filter_view()  # 筛选看板算完 → 刷新它
        elif module == "analysis.text_report":
            self.load_text_report()  # 文本分析算完 → 刷新它
        elif module == "extract.documents":
            self.log.appendPlainText("[提示] 抽取完成，接着生成图表…")
            self.run_module("analysis.text_report")   # 一步到位：抽完直接出图表
        else:
            # 采集/报告跑完：数据变了，顺手把筛选看板也重算一遍（它算完会自己切过去）
            latest = self.latest_report_dir()
            self.log.appendPlainText(
                "[提示] 数据更新了，正在刷新「筛选看板」…"
                + (f"（新报告在 reports/{latest.name}/）" if latest else ""))
            self.generate_filter_view()

    def on_error(self, message: str) -> None:
        """进程启动失败时也要恢复按钮，否则界面会卡在"禁用"状态。"""
        self.log.appendPlainText(f"\n[启动失败] {message}")
        self.btn_collect.setEnabled(True)
        self.btn_report.setEnabled(True)
        self.btn_txt_extract.setEnabled(True)
        self.btn_txt_report.setEnabled(True)
        self._refresh_stop_button()

    # ==================== 停止 ====================
    def stop_tasks(self) -> None:
        """停止按钮：把正在跑的网页抓取 / 采集 / 报告都停掉。"""
        stopped = []
        crawler = getattr(self, "crawler", None)
        if crawler is not None and crawler.isRunning():
            crawler.stop()
            stopped.append("网页抓取")
        runner = getattr(self, "runner", None)
        if runner is not None and runner.is_running():
            runner.stop()
            stopped.append("采集/报告/文本分析")

        if stopped:
            self.log.appendPlainText(
                f"[停止] 已请求停止：{'、'.join(stopped)}（当前这一页/这一步会收尾，随后停下）")
        else:
            self.log.appendPlainText("[提示] 现在没有正在跑的任务。")
        self._refresh_stop_button()

    def _refresh_stop_button(self) -> None:
        """只要有任务在跑，停止按钮就能点。"""
        crawler = getattr(self, "crawler", None)
        runner = getattr(self, "runner", None)
        busy = bool((crawler is not None and crawler.isRunning())
                    or (runner is not None and runner.is_running()))
        self.btn_stop.setEnabled(busy)

    # ==================== 数据概况 ====================
    def refresh_overview(self) -> None:
        """直接在主线程读磁盘：audit() 只扫目录，毫秒级，不需要线程/进程。"""
        result = audit()
        self.overview.setRowCount(len(result))
        self.overview.setColumnCount(2)
        self.overview.setHorizontalHeaderLabels(["检查项", "数量"])
        for i, (key, items) in enumerate(result.items()):
            self.overview.setItem(i, 0, QTableWidgetItem(key))
            self.overview.setItem(i, 1, QTableWidgetItem(str(len(items))))

    # ==================== 归档报告位置 ====================
    def latest_report_dir(self):
        """reports/ 里最新的一批（目录名就是时间戳，按名字排序即按时间）。

        现在只用来在日志里报一句"归档报告在哪"——图表统一在「筛选看板」页看。
        """
        root = BASE_DIR / "reports"
        dirs = [p for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
        return max(dirs, key=lambda p: p.name) if dirs else None

    # ==================== 托盘（关窗口不退出） ====================
    def app_icon(self) -> QIcon:
        """程序图标：优先用 assets/app.ico，文件不在就退回系统自带图标。"""
        path = BASE_DIR / "assets" / "app.ico"
        if path.is_file():
            return QIcon(str(path))
        return self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    def _build_tray(self) -> None:
        """建托盘图标和右键菜单。

        为什么必须有：开机自启是带 --minimized 起来的，窗口不显示；
        要是连托盘都没有，任务栏里也找不到 → 用户只能去任务管理器杀进程。
        """
        self.tray = QSystemTrayIcon(self.app_icon(), self)
        self.tray.setToolTip("爬虫项目 · 采集与分析")

        self._tray_menu = QMenu()  # ★ 存成属性：菜单被回收了右键就没反应
        act_show = QAction("显示主窗口", self)
        act_show.triggered.connect(self.show_main)
        act_hide = QAction("隐藏到托盘", self)
        act_hide.triggered.connect(self.hide)
        act_quit = QAction("退出程序", self)
        act_quit.triggered.connect(self.quit_app)
        self._tray_menu.addAction(act_show)
        self._tray_menu.addAction(act_hide)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction(act_quit)

        self.tray.setContextMenu(self._tray_menu)
        self.tray.activated.connect(self.on_tray_activated)  # 双击图标也能叫回窗口
        self.tray.show()

    def show_main(self) -> None:
        """把窗口叫回来（托盘菜单 / 双击托盘图标）。"""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_main()

    def quit_app(self) -> None:
        """真正退出：任务还在跑就先问一句，别一抖手把采集掐了。"""
        busy = []
        if getattr(self, "crawler", None) is not None and self.crawler.isRunning():
            busy.append("网页抓取")
        if getattr(self, "runner", None) is not None and self.runner.is_running():
            busy.append("采集/生成报告")
        if busy:
            answer = QMessageBox.question(
                self, "还有任务在跑",
                "、".join(busy) + " 还没结束，确定要退出吗？\n退出后这次任务会被中断。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._really_quit = True
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        """点右上角 × 只是收进托盘，不是退出（想真退出：托盘右键 → 退出程序）。"""
        if self._really_quit or not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()  # 没有托盘的机器不能藏窗口，否则找不回来
            return
        event.ignore()
        self.hide()
        if not self._tray_hinted:  # 第一次提示，免得用户以为程序被关掉了
            self._tray_hinted = True
            self.tray.showMessage("还在后台运行",
                                  "窗口已收进托盘：右键托盘图标可以显示窗口或退出。",
                                  QSystemTrayIcon.MessageIcon.Information, 5000)


def hide_console() -> None:
    """打包后的黑窗藏起来（只藏不关）。

    只在"这个控制台确实是我独占的"时候才藏 —— 从终端里手敲启动时，控制台是那个
    终端窗口的，藏了会把用户的终端（连带报错信息）一起藏掉，出问题就没法排查。
    三条都满足才动手：
      1. 有控制台（双击时 Windows 会给一个，从别的程序里起可能没有）；
      2. 启动我的那个进程没挂在这个控制台上（双击 exe 时父进程是 explorer，它不挂控制台；
         在 cmd / PowerShell 里手敲时，父进程就是那个终端，它挂着 → 不动）；
      3. 控制台上只有我自己（数出来 > 1 说明还有人共用 → 不动）。
    只藏不关：窗口还在 → 子进程的 print 照常工作，运行日志和采集失败判定都不受影响。
    """
    if not FROZEN or sys.platform != "win32":
        return
    import ctypes
    import os
    kernel32 = ctypes.windll.kernel32
    hwnd = kernel32.GetConsoleWindow()
    if not hwnd:
        return  # 压根没有控制台，没什么可藏的
    attached = (ctypes.c_uint32 * 16)()
    count = kernel32.GetConsoleProcessList(attached, 16)
    pids = [attached[i] for i in range(count)]
    if os.getppid() in pids or count > 1:
        return  # 和终端或别的进程共用 → 别动它
    ctypes.windll.user32.ShowWindow(hwnd, 0)


# 整个脚本都是顶层代码的模块（import 即执行，不需要 main()）
TOP_LEVEL_MODULES = {"run_daily"}


def run_task(module: str, extra: list[str] | None = None) -> int:
    """打包后 exe 自己当解释器：CrawlerStudio.exe --task analysis.report。

    ★ 不能用 runpy.run_module()：Nuitka 编译后的模块加载器没有 get_code()，会报
      `AttributeError: type object 'nuitka_module_loader' has no attribute 'get_code'`。
      所以改成"导入模块 → 调它的 main()"：PyInstaller / Nuitka / 开发环境三种情况一致，
      runpy 那行无害的 RuntimeWarning 也顺带没了。

    约定：**凡是要被 --task 跑的模块，都要提供 `main() -> int`**；
    整个脚本都是顶层代码的（run_daily.py 就是）import 的时候已经跑完，不用 main()。
    """
    import importlib

    sys.argv = [module, *(extra or [])]     # ★ 必须改：否则模块会看到 --task 这些参数，
    mod = importlib.import_module(module)   #   像 run_daily 会把 --task 当成"站点名"
    entry = getattr(mod, "main", None)
    if entry is None:
        if module in TOP_LEVEL_MODULES:
            return 0                        # 顶层脚本：import 时已经执行完
        print(f"[错误] {module} 没有 main()，什么都没执行（请给它加一个 main() -> int）")
        return 1
    return int(entry() or 0)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--task":  # ★ 被自己当解释器调起来
        rest = sys.argv[3:]
        if "--silent" in rest:  # 定时任务专用：把黑窗藏掉
            hide_console()
            rest = [a for a in rest if a != "--silent"]
        sys.exit(run_task(sys.argv[2], rest))

    hide_console()  # ★ 先藏黑窗，再建界面
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # ★ 关窗口只是收进托盘，程序别退
    win = MainWindow()
    if "--minimized" in sys.argv:  # 开机自启用：启动就躲进托盘
        win.hide()
    else:
        win.show()
    if not QSystemTrayIcon.isSystemTrayAvailable():  # 没有托盘的机器（少见）必须给窗口
        win.show()
    sys.exit(app.exec())
