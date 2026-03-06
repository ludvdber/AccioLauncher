# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec pour Accio Launcher — mode onefile, windowed."""

import os

block_cipher = None

ROOT = os.path.abspath(".")

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "src", "data", "games.json"), os.path.join("data")),
        (os.path.join(ROOT, "assets"), "assets"),
        (os.path.join(ROOT, "assets", "7z"), os.path.join("assets", "7z")),
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AccioLauncher",
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
    icon=os.path.join(ROOT, "assets", "accio_launcher.ico"),
)
