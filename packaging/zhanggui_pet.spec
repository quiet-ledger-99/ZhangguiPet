# -*- mode: python ; coding: utf-8 -*-
# 掌柜台桌宠 打包配置（onedir + zip；单个 exe 更容易被杀毒误报）。
# 用法（在仓库根目录）：.venv\Scripts\python -m PyInstaller --noconfirm --clean packaging\zhanggui_pet.spec
# 路径都按本文件所在位置算（PyInstaller 的相对路径是相对 spec 的，不是当前目录）。
import os
ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
HERE = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(ROOT, 'zhanggui_pet.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, 'assets'), 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtSql', 'PySide6.QtTest',
              'PySide6.QtOpenGL', 'PySide6.QtPdf', 'PySide6.QtSvg', 'PySide6.QtConcurrent', 'PySide6.QtDBus',
              'PySide6.QtXml', 'PySide6.QtHelp', 'PySide6.QtPrintSupport', 'PySide6.QtQuickWidgets',
              'PySide6.QtOpenGLWidgets', 'numpy', 'PIL', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ZhangguiPet',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(ROOT, 'assets', 'icon.ico')],
    version=os.path.join(HERE, 'version_info.txt'),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ZhangguiPet',
)
