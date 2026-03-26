# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for wa_combiner
# Build with: pyinstaller wa_combiner.spec

a = Analysis(
    ['wa_combiner.py'],
    pathex=[],
    binaries=[],
    datas=[('DejaVuSans.ttf', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='wa_combiner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,
)
