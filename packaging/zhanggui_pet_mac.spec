# -*- mode: python ; coding: utf-8 -*-
# 掌柜台桌宠 macOS 打包配置（onedir -> ZhangguiPet.app）。由 packaging/build_mac.sh 调用，不要直接跑。
# 图标 build/ZhangguiPet.icns 由 build_mac.sh 从 assets/icon.png 现做（不进仓库）。
import os
ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
VERSION = os.environ.get('ZGP_VERSION', '0.3.10')
ICNS = os.path.join(ROOT, 'build', 'ZhangguiPet.icns')

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
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ZhangguiPet', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          argv_emulation=False, target_arch='arm64', codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ZhangguiPet')
app = BUNDLE(
    coll,
    name='ZhangguiPet.app',
    icon=ICNS if os.path.exists(ICNS) else None,
    bundle_identifier='local.ZhangguiPet',
    version=VERSION,
    info_plist={
        'CFBundleDisplayName': '掌柜台桌宠',
        'CFBundleShortVersionString': VERSION,
        'LSUIElement': True,                 # 不在 Dock 里出现，只在菜单栏有图标
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
    },
)
