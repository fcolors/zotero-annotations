@echo off
REM build_exe.bat — 一键打包 zotero_annotations_cli（Windows，onedir 单一文件夹）
REM 产物：dist\zotero_annotations_cli\zotero_annotations_cli.exe （整目录自包含）
REM 前提：本机已安装 Python 3 + pip install pyinstaller pyinstaller-hooks-contrib pymupdf
REM 用法：双击或 cmd 里执行  build_exe.bat
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 未找到 python，请先安装 Python 3 并加入 PATH
    exit /b 1
)

python -m pip show pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [INFO] 安装 PyInstaller ...
    python -m pip install pyinstaller pyinstaller-hooks-contrib
)

echo [INFO] 打包中（约 1-2 分钟）...
python -m PyInstaller zotero_annotations_cli.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERROR] 打包失败，见上方输出
    exit /b 1
)

echo.
echo [OK] 产物目录：dist\zotero_annotations_cli\
echo      用法（单一命令，给上下文参数即进入上下文模式）：
echo        dist\zotero_annotations_cli\zotero_annotations_cli.exe --key ITEM_KEY
echo        dist\zotero_annotations_cli\zotero_annotations_cli.exe --key ITEM_KEY --color red
echo        dist\zotero_annotations_cli\zotero_annotations_cli.exe --key ITEM_KEY --fulltext --export-pdf
echo      分发给其它机器时，把整个 dist\zotero_annotations_cli 目录一起拷贝即可。
endlocal
