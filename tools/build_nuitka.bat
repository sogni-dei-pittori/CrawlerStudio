@echo off
REM --- CrawlerStudio: INCREMENTAL rebuild (fast, keeps old build output) ---
REM English only in .bat files (cmd parses them as ANSI).
cd /d "%~dp0.."

echo ============================================================
echo  CrawlerStudio - INCREMENTAL rebuild with Nuitka
echo  (keeps build_nuitka; only changed modules get recompiled)
echo ============================================================
echo.
echo Building... do NOT close this window.
echo First build from scratch takes 20-40 min; an incremental one ~3-10 min.
echo.

.venv\Scripts\python.exe -m nuitka ^
  --standalone --enable-plugin=pyside6 --windows-console-mode=force ^
  --output-dir=build_nuitka --output-filename=CrawlerStudio.exe ^
  --include-package-data=pyecharts ^
  --include-data-dir=assets=assets ^
  --include-data-dir=charts\assets=charts\assets ^
  --include-module=run_daily --include-module=baidu_api --include-module=bilibili_rank ^
  --include-module=douban_boards --include-module=juejin_api --include-module=toutiao_api ^
  --include-package=analysis --include-package=extract --include-package=warehouse ^
  --nofollow-import-to=matplotlib --nofollow-import-to=streamlit --nofollow-import-to=selenium ^
  --company-name="Personal Study Project" --product-name="CrawlerStudio" ^
  --file-version=0.3.0 --product-version=0.3.0 ^
  --windows-icon-from-ico=assets\app.ico ^
  --jobs=8 --lto=no ^
  main.py

echo.
echo ============================================================
echo  Exit code: %ERRORLEVEL%   (0 = success)
echo  Output   : build_nuitka\main.dist\CrawlerStudio.exe
echo ============================================================
echo.
echo  Note: the app reads and writes data NEXT TO THE EXE.
echo  If main.dist\data is missing after a clean rebuild, copy it:
echo     robocopy data "build_nuitka\main.dist\data" /E
echo.
pause
