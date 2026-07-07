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
    # Ces paquets ne sont tirés QUE par la CLI optionnelle de httpx (`httpx._main`
    # → rich/pygments/click/PIL/numpy), jamais utilisée au runtime. Vérifié par
    # grep : aucun import direct dans src/. ~40 Mo non compressés en moins.
    # tkinter : jamais utilisé (app 100 % PyQt6).
    excludes=[
        "numpy", "PIL", "rich", "pygments", "markdown_it", "mdurl",
        "click", "tkinter", "_tkinter",
    ],
    cipher=block_cipher,
    noarchive=False,
)


def _keep(entry):
    """Filtre des binaires/datas Qt inutiles (aucune fonctionnalité du launcher
    ne les touche) : traductions Qt (dialogues natifs non utilisés), module PDF."""
    name = entry[0].lower()
    if name.startswith("pyqt6\\qt6\\translations"):
        return False
    if "qt6pdf" in name:
        return False
    return True


a.binaries = [e for e in a.binaries if _keep(e)]
a.datas = [e for e in a.datas if _keep(e)]

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
