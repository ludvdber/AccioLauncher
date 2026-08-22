# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec pour Accio Launcher — mode onefile, windowed."""

import os
import re

block_cipher = None

ROOT = os.path.abspath(".")


# ─── Ressource de version Windows ───
# Sans elle, les propriétés du fichier n'affichent ni produit, ni version, ni
# auteur : ça nuit à la crédibilité auprès de l'utilisateur ET au score de
# réputation SmartScreen d'un binaire non signé. Générée ici depuis APP_VERSION
# pour qu'elle ne puisse jamais diverger de la version du code.

def _app_version() -> str:
    """Lit APP_VERSION dans src/core/config.py (pas d'import : zéro effet de bord)."""
    src = open(os.path.join(ROOT, "src", "core", "config.py"), encoding="utf-8").read()
    m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', src, re.MULTILINE)
    if not m:
        raise SystemExit("APP_VERSION introuvable dans src/core/config.py")
    return m.group(1)


def _write_version_file() -> str:
    """Écrit la ressource VS_VERSION_INFO et retourne son chemin."""
    version = _app_version()
    # Le format Windows exige 4 entiers ; APP_VERSION en compte 3 (0.5.2 → 0.5.2.0).
    nums = [int(p) for p in version.split(".")][:4]
    nums += [0] * (4 - len(nums))
    quad = tuple(nums)
    dotted = ".".join(str(n) for n in quad)

    # ASCII only : la ressource VS_VERSION_INFO est relue par PyInstaller puis
    # affichée par l'explorateur Windows ; un tiret cadratin y ressort en « ? ».
    content = f"""# Genere par accio_launcher.spec - ne pas editer a la main.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={quad},
    prodvers={quad},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040c04b0',
        [StringStruct('CompanyName', 'ASTeam'),
        StringStruct('FileDescription', 'Accio Launcher - launcher des jeux Harry Potter'),
        StringStruct('FileVersion', '{dotted}'),
        StringStruct('InternalName', 'AccioLauncher'),
        StringStruct('LegalCopyright', 'Copyright (c) 2026 ASTeam. Licence MIT.'),
        StringStruct('OriginalFilename', 'AccioLauncher.exe'),
        StringStruct('ProductName', 'Accio Launcher'),
        StringStruct('ProductVersion', '{dotted}')])
      ]),
    VarFileInfo([VarStruct('Translation', [0x40c, 1200])])
  ]
)
"""
    out_dir = os.path.join(ROOT, "build")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "version_info.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


VERSION_FILE = _write_version_file()


a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "src", "data", "games.json"), os.path.join("data")),
        (os.path.join(ROOT, "src", "data", "i18n"), os.path.join("data", "i18n")),
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
    """Filtre des donnees inutiles a l'execution.

    Traductions Qt (dialogues natifs non utilises), module PDF, et surtout
    les BANDES-ANNONCES : deux d'entre elles faisaient passer l'exe de 74 a
    160 Mo, et les huit l'auraient mene au-dela de 500 Mo pour un ornement
    facultatif. Elles se telechargent desormais depuis les assets de release
    (voir src/core/trailers.py). Le dossier reste dans l'arbre de travail :
    il sert au developpement et a la fabrication des videos.

    Les chemins sont normalises AVANT comparaison : PyInstaller les donne
    avec le separateur de la plateforme, et un filtre ecrit en antislash ne
    correspondrait a rien le jour ou le build tournera sous Linux.
    """
    chemin = entry[0].lower().replace("\\", "/")
    if chemin.startswith("pyqt6/qt6/translations"):
        return False
    if "qt6pdf" in chemin:
        return False
    if chemin.startswith("assets/videos"):
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
    # upx=False VOLONTAIREMENT : la compression UPX d'un exe PyInstaller est un
    # déclencheur classique de faux positifs heuristiques (Defender & co.), et
    # sur un binaire non signé ça suffit à faire fuir les premiers utilisateurs.
    # Les vraies économies de taille sont ailleurs (excludes ci-dessus, poids
    # des assets vidéo). NE PAS repasser à True sans certificat de signature.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "accio_launcher.ico"),
    version=VERSION_FILE,
)
