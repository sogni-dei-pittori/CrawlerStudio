@echo off
REM Rebuild CrawlerStudio with Nuitka. First run takes 20-40 minutes.
REM English only in .bat files (cmd parses them as ANSI).
cd /d "%~dp0.."

echo ============================================
echo  Removing previous build output...
echo ============================================
if exist build_nuitka rmdir /s /q build_nuitka

echo.
echo ============================================
echo  Building with Nuitka (do not close this window)
echo ============================================
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
  --file-version=0.2.0 --product-version=0.2.0 ^
  --windows-icon-from-ico=assets\app.ico ^
  --jobs=8 --lto=no ^
  main.py

echo.
echo ============================================
echo  Exit code: %ERRORLEVEL%
echo  Output   : build_nuitka\main.dist\CrawlerStudio.exe
echo ============================================
pause
