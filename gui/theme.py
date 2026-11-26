"""全局浅色主题 v2：亚克力玻璃质感（模拟），只管外观，不碰任何业务逻辑。

用法（main.py 的 run_gui 里，QApplication 建好之后）：
    from gui.theme import apply_theme
    apply_theme(app)

设计语言（玻璃拟态 / Dribbble 风）：
    - 窗口底是冷灰蓝渐变，内容区是一整块半透明白玻璃卡片（rgba 150/255）
      + 1px 白色细边框 + 14px 大圆角；控件全部半透明白，压出「玻璃叠层」。
    - 标签页做成药丸（pill）样式：未选中半透明白、选中近实白 + 蓝字。
    - 高弧度圆角：按钮/输入 8px，表格/树/日志 10px，内容卡片 14px；
      窗口四角的圆角由 Windows 11 DWM 负责，程序不干预。
    - 已知边界（如实说明）：
      * 真·穿窗高斯模糊（系统级 Acrylic）需要 DWM 透明窗口，在 Qt Widgets
        里风险高（黑窗/内容不可见事故率不低），此文件不做；用染色半透明模拟。
      * QSS 不支持 box-shadow，卡片投影无法绘制；窗口级投影由系统自带。
    - 主按钮（蓝渐变白字）= objectName "primary"，危险按钮（红字）= "danger"，
      由 main_window.py 用 setObjectName 标注；斑马纹颜色也写在这里。
    - 删掉这个文件、去掉 main.py 里那一行，程序行为完全不变，只是变回系统默认脸。
"""
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

APP_QSS = """
/* ============ 窗口与通用 ============ */
QMainWindow, QDialog {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f3f6fb, stop:1 #e4eaf4);
}
QToolTip {
    border: 1px solid #ffffff;
    background: rgba(252, 253, 255, 246);
    color: #1f2328;
    padding: 5px 10px;
    border-radius: 4px;
}

/* ============ 按钮：半透明白玻璃，主/危按钮特殊化 ============ */
QPushButton {
    background: rgba(255, 255, 255, 168);
    border: 1px solid rgba(255, 255, 255, 255);
    border-radius: 8px;
    padding: 5px 16px;
    color: #2b3440;
}
QPushButton:hover {
    background: rgba(255, 255, 255, 235);
    border-color: #9ec2f7;
    color: #1a73e8;
}
QPushButton:pressed { background: rgba(214, 228, 250, 220); }
QPushButton:disabled {
    background: rgba(255, 255, 255, 90);
    border-color: rgba(255, 255, 255, 150);
    color: #9aa3ad;
}
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #3b82f0, stop:1 #1a6ae0);
    border-color: rgba(255, 255, 255, 200);
    color: #ffffff;
    font-weight: 600;
}
QPushButton#primary:hover { background: #2f7ae8; }
QPushButton#primary:pressed { background: #1f62cf; }
QPushButton#primary:disabled {
    background: rgba(122, 168, 235, 160);
    border-color: rgba(255, 255, 255, 140);
    color: rgba(255, 255, 255, 220);
}
QPushButton#danger {
    background: rgba(255, 255, 255, 168);
    border-color: rgba(255, 255, 255, 255);
    color: #c0392b;
}
QPushButton#danger:hover { background: rgba(253, 240, 239, 235); border-color: #e2a49e; }
QPushButton#danger:disabled {
    background: rgba(255, 255, 255, 90);
    border-color: rgba(255, 255, 255, 150);
    color: #cfb6b2;
}

/* ============ 输入类控件：磨砂白底 + 白描边 ============ */
QLineEdit, QSpinBox, QComboBox, QDateEdit {
    background: rgba(252, 253, 255, 200);
    border: 1px solid rgba(255, 255, 255, 255);
    border-radius: 8px;
    padding: 4px 10px;
    selection-background-color: #cfe0fb;
    selection-color: #1f2328;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus {
    border-color: #7faef2;
    background: rgba(255, 255, 255, 245);
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled, QDateEdit:disabled {
    background: rgba(255, 255, 255, 90);
    color: #9aa3ad;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #e2e8f2;
    selection-background-color: #e8f0fe;
    selection-color: #1a73e8;
    outline: 0;
}

/* ============ 标签页：药丸标签 + 玻璃卡片内容区 ============ */
QTabWidget::pane {
    background: rgba(255, 255, 255, 150);
    border: 1px solid rgba(255, 255, 255, 255);
    border-radius: 14px;
}
QTabBar { background: transparent; }
QTabBar::tab {
    background: rgba(255, 255, 255, 96);
    color: #55606e;
    padding: 6px 18px;
    margin-right: 6px;
    border: 1px solid rgba(255, 255, 255, 180);
    border-radius: 9px;
}
QTabBar::tab:hover {
    color: #1a73e8;
    background: rgba(255, 255, 255, 170);
}
QTabBar::tab:selected {
    background: rgba(255, 255, 255, 242);
    color: #1a73e8;
    font-weight: 600;
    border: 1px solid #ffffff;
}

/* ============ 表格与树：近实白圆角卡片 ============ */
QTableWidget {
    background: rgba(255, 255, 255, 214);
    alternate-background-color: rgba(240, 245, 252, 140);
    gridline-color: rgba(190, 200, 215, 90);
    border: 1px solid rgba(255, 255, 255, 255);
    border-radius: 10px;
    selection-background-color: #d8e7fd;
    selection-color: #1f2328;
}
QHeaderView::section {
    background: rgba(255, 255, 255, 160);
    color: #47525f;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid rgba(200, 210, 225, 90);
    border-bottom: 1px solid rgba(255, 255, 255, 255);
    font-weight: 600;
}
QTableCornerButton::section { background: rgba(255, 255, 255, 160); border: none; }
QTreeView {
    background: rgba(255, 255, 255, 190);
    border: 1px solid rgba(255, 255, 255, 255);
    border-radius: 10px;
    outline: 0;
}
QTreeView::item { padding: 3px 2px; }
QTreeView::item:hover { background: rgba(220, 232, 250, 130); }
QTreeView::item:selected { background: #d8e7fd; color: #1f2328; }

/* ============ 日志 / 文本区：磨砂玻璃 ============ */
QPlainTextEdit, QTextBrowser {
    background: rgba(255, 255, 255, 176);
    border: 1px solid rgba(255, 255, 255, 255);
    border-radius: 10px;
    padding: 8px;
    selection-background-color: #cfe0fb;
    selection-color: #1f2328;
}

/* ============ 分割条与滚动条：半透明细条 ============ */
QSplitter::handle { background: rgba(255, 255, 255, 110); }
QSplitter::handle:horizontal { width: 6px; }
QSplitter::handle:vertical { height: 6px; }
QSplitter::handle:hover { background: rgba(158, 194, 247, 150); }
QScrollBar:vertical {
    background: rgba(255, 255, 255, 60);
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: rgba(130, 142, 160, 120);
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(110, 122, 140, 170); }
QScrollBar:horizontal {
    background: rgba(255, 255, 255, 60);
    height: 10px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: rgba(130, 142, 160, 120);
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: rgba(110, 122, 140, 170); }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ============ 菜单：弹层保持实底（半透明弹窗在 Windows 易出黑角）============ */
QMenu {
    background: #ffffff;
    border: 1px solid #e2e8f2;
    padding: 5px;
}
QMenu::item { padding: 5px 24px 5px 12px; border-radius: 4px; }
QMenu::item:selected { background: #e8f0fe; color: #1a73e8; }
QMenu::separator { height: 1px; background: #eceef2; margin: 4px 8px; }
"""


def apply_theme(app: QApplication) -> None:
    """把主题挂到应用上：统一中文字体 + 一份 QSS。只动外观，可整体撤销。"""
    app.setFont(QFont("Microsoft YaHei UI", 10))  # Windows 全平台自带，中文渲染一致
    app.setStyleSheet(APP_QSS)
