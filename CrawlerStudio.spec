# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('pyecharts')

# ---- 用不到的 Python 包（模拟排除验证过：全堵住也能正常跑）----
EXCLUDES = [
    # 画图 / 字体 / 交互式那一套，本项目一个都没用（图表是 pyecharts 出 HTML）
    'matplotlib', 'matplotlib_inline', 'contourpy', 'kiwisolver', 'cycler',
    'PIL', 'IPython', 'jedi', 'parso', 'prompt_toolkit', 'traitlets',
    'stack_data', 'asttokens', 'pure_eval', 'executing',
    # 装机时顺手装上、和本项目无关的
    'seaborn', 'streamlit', 'selenium', 'trafilatura', 'psutil', 'pytest',
    'anyio', 'trio', 'tornado', 'uvicorn', 'starlette', 'altair', 'pydeck',
    'watchdog', 'websockets', 'dateparser', 'courlan', 'htmldate', 'justext',
]


def keep_data(dest_name: str) -> bool:
    """资源过滤：丢掉运行时用不到的 Qt 大文件。"""
    low = dest_name.replace('\\', '/').lower()
    if '.debug.' in low:
        return False            # qtwebengine_devtools_resources.debug.pak（72MB）等调试版资源
    if 'pyside6/translations/' in low:
        return False            # Qt 自带的 157 个 .qm 语言包（52MB）
    return True


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['run_daily', 'analysis.report', 'analysis.live_view', 'baidu_api', 'bilibili_rank', 'douban_boards', 'juejin_api', 'toutiao_api'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
# ---- 资源过滤：让上面 keep_data() 生效（COLLECT 用的就是 a.datas）----
_before = len(a.datas)
a.datas = [item for item in a.datas if keep_data(item[0])]
print(f'[spec] 资源过滤：{_before} -> {len(a.datas)} 个（丢掉 {_before - len(a.datas)} 个）')

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CrawlerStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['assets/app.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CrawlerStudio',
)
