# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Custom_Quiz
# Build: pyinstaller Custom_Quiz.spec

block_cipher = None

a = Analysis(
    ['server.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('index.html',   '.'),
        ('browse.html',  '.'),
        ('quiz.html',    '.'),
        ('review.html',  '.'),
        ('wrong.html',   '.'),
        ('css',          'css'),
        ('js',           'js'),
        ('questions',    'questions'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Custom_Quiz',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # 顯示終端機視窗（用來看伺服器 URL）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Custom_Quiz',
)
