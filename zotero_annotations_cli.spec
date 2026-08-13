# -*- mode: python ; coding: utf-8 -*-
# zotero_annotations_cli.spec — PyInstaller 打包配置（onedir 单一文件夹）
#
# 打包合并版 CLI（zotero_annotations_cli.py）为 onedir 输出：
#   dist/zotero_annotations_cli/zotero_annotations_cli.exe + 依赖 DLL
# 这是一个自包含的单一文件夹，整目录拷贝/压缩即可分发，免装 Python/PyMuPDF。
#
# 用法： python3 -m PyInstaller zotero_annotations_cli.spec --noconfirm --clean
#   （Windows 下也可直接运行 build_exe.bat）
#
# 已踩过的坑与解决（2026-08-13 实测通过）：
#   1) 单一入口：zotero_annotations.py 与 zotero_context.py 已合并为一个脚本，
#      Analysis 只需指向 zotero_annotations_cli.py，不再有动态兄弟模块导入问题。
#   2) PyMuPDF：pyinstaller-hooks-contrib 提供官方 hook，需先
#      pip install pyinstaller pyinstaller-hooks-contrib。警告里的 pandas/cppyy/
#      mupdf_cppyy 等缺失均为可选功能（表格提取等），不影响文本提取，可忽略；
#      并在 excludes 里显式排除以减小体积。
#   3) onedir vs onefile：选 onedir（单一文件夹）。启动更快、免临时解压、
#      更少杀毒误报；代价是一整个文件夹而非单个 exe 文件。要单文件可改回
#      onefile 写法（EXE 直接收集 a.binaries/a.datas）。
#   4) 杀毒软件误报：PyInstaller 打包产物常见误报，属正常，可加白名单。
#   5) 平台绑定：Windows 打的 exe 只能在 Windows x64 跑；跨平台要在目标平台重打。
#   6) 产物不提交仓库：dist/ 已在 .gitignore 忽略，只保留本 spec 与 build_exe.bat。

a = Analysis(
    ['skills/zotero-annotations-cli/scripts/zotero_annotations_cli.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pandas', 'numpy', 'cppyy', 'mupdf_cppyy'],  # PyMuPDF 可选依赖，按需排除减小体积
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir：二进制由 COLLECT 收集
    name='zotero_annotations_cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,            # 命令行工具，需要 stdout
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='zotero_annotations_cli',   # 单一文件夹：dist/zotero_annotations_cli/
)
