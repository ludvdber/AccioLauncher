# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec pour Accio Launcher.

Windows : un seul `AccioLauncher.exe` (onefile, windowed) — inchangé.
Linux : un DOSSIER (onedir), que `build/linux/appimage.sh` range dans une
AppImage. Pas de onefile là-bas : l'AppImage est déjà un fichier unique et
compressé, et un onefile dedans se décompresserait EN PLUS dans /tmp à
chaque démarrage (~200 Mo écrits pour rien, et plusieurs secondes).
"""

import os
import re
import sys

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
        StringStruct('LegalCopyright', 'Copyright (c) 2026 ASTeam. GNU GPL v3.'),
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
    # brotli : httpx l'importe S'IL LE TROUVE, et il n'était là que parce que
    # py7zr, retiré du projet, restait installé sur le poste de build. L'exe
    # construit ici le portait, celui de la CI non : le contenu d'un build ne
    # doit pas dépendre de ce qui traîne sur la machine. httpx s'en passe (gzip).
    excludes=[
        "numpy", "PIL", "rich", "pygments", "markdown_it", "mdurl",
        "click", "tkinter", "_tkinter", "brotli", "_brotli",
    ],
    cipher=block_cipher,
    noarchive=False,
)


# ─── Ce que Qt embarque d'office et que ce launcher n'atteint jamais ───
# Relevé le 2026-09-23 sur l'exe 1.0.5 (51,85 Mo) en recompressant chaque
# fichier de sa table des matières : le code et les assets du projet n'y
# pesaient que 18 %, le reste était le moteur — dont ceci, mort. Ce qui doit
# RESTER est tenu par tests/test_spec_build.py : un filtre trop gourmand ne
# casserait que l'exe, jamais la suite, qui tourne depuis les sources.
_JAMAIS_ATTEINTS = (
    # Mesa, le rendu OpenGL LOGICIEL : 20,6 Mo bruts, 7,6 Mo dans l'exe, soit
    # plus que toutes nos images réunies. L'interface est peinte au raster et
    # la vidéo sort par QVideoSink ; seul `qwindows.dll` nomme ce fichier, en
    # chargement à la demande. Vérifié en lançant l'exe (2026-09-24) : la
    # conversion vidéo passe par Direct3D 11, et même sous QT_OPENGL=software
    # aucune bibliothèque OpenGL n'est chargée — le 1.0.5, qui l'avait, ne l'a
    # jamais ouvert non plus. Interface FORCÉE en OpenGL : Qt retombe sur le
    # pilote, rendu identique.
    "bin/opengl32sw.dll",
    # Décodeurs d'image : les assets ne sont que JPEG, PNG (intégré à QtGui),
    # ICO et SVG. qpdf.dll partait même sans Qt6Pdf.dll, que ce filtre écarte
    # déjà : il ne pouvait pas se charger.
    "imageformats/qgif.dll", "imageformats/qicns.dll", "imageformats/qpdf.dll",
    "imageformats/qtga.dll", "imageformats/qtiff.dll",
    "imageformats/qwbmp.dll", "imageformats/qwebp.dll",
    # QtNetwork ne sert qu'à l'instance unique (QLocalServer) : les
    # téléchargements passent par httpx et l'OpenSSL de Python, jamais par la
    # pile TLS de Qt.
    "tls/qopensslbackend.dll", "tls/qschannelbackend.dll",
    "tls/qcertonlybackend.dll", "networkinformation/qnetworklistmanager.dll",
    # Tactile TUIO (par UDP) et plateformes de test : jamais chargés par l'exe.
    "generic/qtuiotouchplugin.dll", "platforms/qminimal.dll",
    "platforms/qoffscreen.dll",
    # ── Linux (AppImage) : les mêmes, sous leur nom Linux ──
    "imageformats/libqgif.so", "imageformats/libqicns.so", "imageformats/libqpdf.so",
    "imageformats/libqtga.so", "imageformats/libqtiff.so",
    "imageformats/libqwbmp.so", "imageformats/libqwebp.so",
    "tls/libqopensslbackend.so", "tls/libqcertonlybackend.so",
    "networkinformation/libqnetworkmanager.so", "networkinformation/libqconnman.so",
    "networkinformation/libqglib.so",
    "generic/libqtuiotouchplugin.so", "platforms/libqminimal.so",
    "platforms/libqoffscreen.so",
    # Plateformes d'écran EMBARQUÉ (framebuffer, EGL sans compositeur, VNC,
    # Vulkan direct) et leurs entrées evdev : un bureau passe par Wayland ou
    # X11 (`libqwayland`, `libqxcb`) — le mode Jeu de Bazzite aussi, Gamescope
    # étant un compositeur.
    "platforms/libqeglfs.so", "platforms/libqlinuxfb.so", "platforms/libqvnc.so",
    "platforms/libqminimalegl.so", "platforms/libqvkkhrdisplay.so",
    "egldeviceintegrations/libqeglfs-emu-integration.so",
    "egldeviceintegrations/libqeglfs-x11-integration.so",
    "generic/libqevdevkeyboardplugin.so", "generic/libqevdevmouseplugin.so",
    "generic/libqevdevtabletplugin.so", "generic/libqevdevtouchplugin.so",
    # Thème GTK 3 : il tirait TOUTE la pile GTK de la machine de build (23
    # bibliothèques, 14,9 Mo), qui aurait lu les thèmes et modules GTK de la
    # machine de l'utilisateur. L'interface est peinte par le launcher :
    # ce greffon ne lui apporte rien. `build/linux/dependances.elaguer` retire
    # ensuite ce qui ne servait qu'à lui.
    "platformthemes/libqgtk3.so",
)


def _keep(entry):
    """Filtre des donnees inutiles a l'execution.

    Traductions Qt, module PDF, les BANDES-ANNONCES, et ce que Qt embarque
    sans que le launcher l'atteigne jamais (_JAMAIS_ATTEINTS ci-dessus).

    ATTENTION au motif des traductions Qt : il a longtemps ete ecrit ici
    « dialogues natifs non utilises », et c'etait FAUX. Les boutons standard
    de QMessageBox (Yes / No / Ok) sont traduits par `qtbase_<langue>.qm` et
    par rien d'autre : les ecarter du build faisait sortir « Yes » et « No »
    en anglais dans un launcher regle en francais (signale le 2026-09-23).
    Le filtre est juste DEPUIS que plus aucun dialogue n'emploie de bouton
    standard : ils portent tous un libelle passe par `tr()`, donc traduit par
    `src/data/i18n/`. Remettre un bouton standard quelque part remettrait de
    l'anglais ici — d'ou le balayage AST de `tests/test_boutons_de_dialogue`.

    Les bandes-annonces : deux d'entre elles faisaient passer l'exe de 74 a
    160 Mo, et les huit l'auraient mene au-dela de 500 Mo pour un ornement
    facultatif. Elles se telechargent desormais depuis les assets de release
    (voir src/core/trailers.py). Le dossier reste dans l'arbre de travail :
    il sert au developpement et a la fabrication des videos.

    Les chemins sont normalises AVANT comparaison : PyInstaller les donne
    avec le separateur de la plateforme, et un filtre ecrit en antislash ne
    correspondrait a rien le jour ou le build tournera sous Linux.
    """
    import sys as _sys

    chemin = entry[0].lower().replace("\\", "/")
    # 7-Zip : chaque plateforme n'embarque que le sien. 7z.exe et 7z.dll ne
    # tournent pas sous Linux, `7zzs` (7-Zip officiel pour Linux) pas sous
    # Windows : 3,7 Mo morts dans l'exe, 1,9 dans l'AppImage. Le build Windows
    # reste ainsi exactement ce qu'il était avant le portage.
    if chemin.startswith("assets/7z/linux/"):
        return _sys.platform != "win32"
    if chemin in ("assets/7z/7z.exe", "assets/7z/7z.dll"):
        return _sys.platform == "win32"
    if chemin.startswith("pyqt6/qt6/translations"):
        return False
    if "qt6pdf" in chemin:
        return False
    if chemin.startswith("assets/videos"):
        return False
    if chemin.endswith(_JAMAIS_ATTEINTS):
        return False
    return True


a.binaries = [e for e in a.binaries if _keep(e)]
a.datas = [e for e in a.datas if _keep(e)]

if sys.platform.startswith("linux"):
    # Ce que la machine fournit, et ce que plus rien n'atteint une fois les
    # greffons écartés : voir build/linux/dependances.py.
    sys.path.insert(0, os.path.join(ROOT, "build", "linux"))
    from dependances import elaguer

    a.binaries, _retires = elaguer(a.binaries)
    print(f"[accio] {len(_retires)} bibliotheques laissees a la machine :",
          ", ".join(sorted(os.path.basename(e[0]) for e in _retires)))

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform.startswith("linux"):
    # strip=True : le Python d'`actions/setup-python` (celui de la release)
    # livre `libpython` et ses modules natifs AVEC leurs symboles de débogage
    # — 33 Mo pour libpython seule, contre 7 une fois épurée. Relevé sur le
    # build d'essai : AppImage de 77 Mo, contre 62 depuis un Python de
    # distribution. Les bibliothèques de Qt sont déjà épurées : rien n'y change.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="AccioLauncher",
        debug=False,
        bootloader_ignore_signals=False,
        strip=True,
        upx=False,
        console=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=True,
        upx=False,
        name="AccioLauncher",
    )
else:
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
        # Les vraies économies de taille sont ailleurs (excludes et
        # _JAMAIS_ATTEINTS ci-dessus, bandes-annonces hors de l'exe). NE PAS repasser à True sans certificat de signature.
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
