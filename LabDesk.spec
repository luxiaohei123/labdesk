# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPECPATH).resolve()

a = Analysis(
    [str(project_root / 'labdesk.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / 'core'), 'core'),
        (str(project_root / 'assets'), 'assets'),
    ],
    hiddenimports=[
        'matplotlib.backends.backend_pdf',
        'matplotlib.backends.backend_svg',
        'matplotlib.backends.backend_agg',
    ],
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
    name='LabDesk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / 'assets' / 'icon.ico') if (project_root / 'assets' / 'icon.ico').exists() else None,
)
