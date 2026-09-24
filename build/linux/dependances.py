"""Dépendances ELF du launcher gelé sous Linux : ce que l'AppImage embarque,
et ce qu'elle laisse à la machine.

PyInstaller copie dans le dossier gelé toute bibliothèque que `ldd` lui
montre sur la machine de BUILD. Deux défauts en découlent, relevés sur un
premier build (2026-09-24) :

- des bibliothèques qu'une AppImage ne doit JAMAIS porter : `libstdc++`,
  `libgcc_s`, fontconfig, freetype, X11… Embarquées depuis Ubuntu 22.04, elles
  passent AVANT celles de la machine ; or les pilotes Mesa de la machine
  (chargés par libEGL/libGL, qui eux viennent bien de la machine) exigent la
  `libstdc++` de LEUR distribution. D'où la liste d'exclusion de la
  communauté AppImage, reprise telle quelle ci-dessous ;
- le greffon `platformthemes/libqgtk3.so` tirait toute la pile GTK 3
  (23 bibliothèques, 14,9 Mo) — une GTK de 22.04 qui lirait les thèmes et les
  modules de la machine. L'interface est entièrement peinte par le launcher :
  ce greffon ne lui apporte rien. `_JAMAIS_ATTEINTS` (spec) l'écarte, et
  `elaguer` retire ce qui ne servait qu'à lui.

`elaguer` ne se fonde sur AUCUNE liste de noms à tenir à jour pour ce second
point : une bibliothèque système n'est gardée que si un module Python, un
greffon Qt ou une bibliothèque de Qt y MÈNE par ses dépendances (`NEEDED`).
Ce qui n'est plus atteint s'en va tout seul.

Utilisé par `accio_launcher.spec` (élagage) et par `build/linux/appimage.py`
(vérification du dossier final). Pur, hormis `besoins` qui lit un fichier.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

# Liste d'exclusion de la communauté AppImage : bibliothèques que TOUTE
# machine de bureau fournit, et qu'il est dangereux d'embarquer. Recopiée de
# `excludelist`, AppImageCommunity/pkg2appimage, commit 19e30b2 (2025-07-21).
FOURNI_PAR_LA_MACHINE = frozenset("""
ld-linux.so.2 ld-linux-x86-64.so.2 libanl.so.1 libBrokenLocale.so.1
libcidn.so.1 libc.so.6 libdl.so.2 libm.so.6 libmvec.so.1 libnss_compat.so.2
libnss_dns.so.2 libnss_files.so.2 libnss_hesiod.so.2 libnss_nisplus.so.2
libnss_nis.so.2 libpthread.so.0 libresolv.so.2 librt.so.1 libthread_db.so.1
libutil.so.1 libstdc++.so.6 libGL.so.1 libEGL.so.1 libGLdispatch.so.0
libGLX.so.0 libOpenGL.so.0 libdrm.so.2 libglapi.so.0 libgbm.so.1 libxcb.so.1
libX11.so.6 libX11-xcb.so.1 libwayland-client.so.0 libasound.so.2
libfontconfig.so.1 libfreetype.so.6 libharfbuzz.so.0 libcom_err.so.2
libexpat.so.1 libgcc_s.so.1 libgpg-error.so.0 libICE.so.6 libSM.so.6
libusb-1.0.so.0 libuuid.so.1 libz.so.1 libjack.so.0 libpipewire-0.3.so.0
libxcb-dri3.so.0 libxcb-dri2.so.0 libfribidi.so.0 libgmp.so.10
""".split()) | frozenset({
    # Écartées par PyInstaller LUI-MÊME (`PyInstaller/depend/dylib.py`, 6.22),
    # qui ne les embarque donc jamais : « un système qui fait tourner un
    # compositeur Wayland les a déjà, dans des versions accordées à ses
    # pilotes ». Sans elles ici, la vérification les réclamerait.
    "libwayland-cursor.so.0", "libwayland-egl.so.1", "libwayland-server.so.0",
    "libcrypt.so.1",
})

_NEEDED = re.compile(r"^\s*NEEDED\s+(\S+)\s*$", re.MULTILINE)


def besoins(chemin: str | os.PathLike) -> list[str]:
    """Les `NEEDED` d'un fichier ELF (vide si ce n'en est pas un).

    Par `objdump`, que PyInstaller exige déjà sous Linux : aucun outil de plus.
    """
    objdump = shutil.which("objdump")
    if objdump is None:
        raise RuntimeError("objdump introuvable (paquet binutils) : PyInstaller l'exige aussi")
    # Programme trouvé par chemin ABSOLU, fichier du build ; aucun shell.
    sortie = subprocess.run(  # nosec B603
        [objdump, "-p", str(chemin)], capture_output=True, text=True, check=False)
    return _NEEDED.findall(sortie.stdout) if sortie.returncode == 0 else []


def _nom(destination: str) -> str:
    return destination.replace("\\", "/").rsplit("/", 1)[-1]


def _systeme(destination: str) -> bool:
    """Bibliothèque tirée de la MACHINE de build : posée à la racine du dossier
    gelé. Tout le reste (PyQt6, Qt, modules Python) vient des paquets."""
    return "/" not in destination.replace("\\", "/")


def elaguer(binaires, lire=besoins):
    """Rend (gardés, retirés) : les entrées `(destination, source, type)` de
    PyInstaller, sans ce que la machine fournit ni ce que plus rien n'atteint.

    Racines : tout ce qui ne vient pas de la machine de build (modules Python,
    PyQt6, bibliothèques et greffons de Qt) et `libpython`, que le chargeur de
    PyInstaller ouvre lui-même. Les liens symboliques restent : ils pointent
    dans PyQt6, qui n'est jamais élagué ici.
    """
    binaires = list(binaires)
    retires = [e for e in binaires if _nom(e[0]) in FOURNI_PAR_LA_MACHINE]
    restants = [e for e in binaires if _nom(e[0]) not in FOURNI_PAR_LA_MACHINE]

    par_nom: dict[str, list] = {}
    for entree in restants:
        par_nom.setdefault(_nom(entree[0]), []).append(entree)
    pile = [e for e in restants
            if not _systeme(e[0]) or e[2] != "BINARY" or _nom(e[0]).startswith("libpython")]
    atteints = {id(e) for e in pile}
    while pile:
        entree = pile.pop()
        if entree[2] == "SYMLINK":
            continue
        for besoin in lire(entree[1]):
            for suivante in par_nom.get(besoin, ()):
                if id(suivante) not in atteints:
                    atteints.add(id(suivante))
                    pile.append(suivante)
    gardes = [e for e in restants if id(e) in atteints]
    retires += [e for e in restants if id(e) not in atteints]
    return gardes, retires


def est_elf(chemin: Path) -> bool:
    try:
        with open(chemin, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def verifier_dossier(dossier: Path, lire=besoins) -> list[str]:
    """Les défauts du dossier gelé, en phrases ; vide s'il est sain.

    - une bibliothèque que la machine doit fournir a été embarquée ;
    - une dépendance n'est NI embarquée NI garantie par la machine : c'est
      « Could not load the Qt platform plugin "xcb" » sur une machine qui
      n'a pas `libxcb-cursor0` — le cas si le runner de build ne l'avait pas
      installée, car PyInstaller ne peut embarquer que ce qu'il voit.
    """
    fichiers = [p for p in dossier.rglob("*") if p.is_file() and not p.is_symlink()]
    presents = {p.name for p in dossier.rglob("*")}
    defauts = [f"embarquée alors que la machine la fournit : {p.relative_to(dossier)}"
               for p in fichiers if p.name in FOURNI_PAR_LA_MACHINE]
    manquants: dict[str, list[str]] = {}
    for p in fichiers:
        if not est_elf(p):
            continue
        for besoin in lire(str(p)):
            if besoin not in presents and besoin not in FOURNI_PAR_LA_MACHINE:
                manquants.setdefault(besoin, []).append(str(p.relative_to(dossier)))
    defauts += [f"dépendance absente : {nom} (requise par {', '.join(sorted(qui)[:3])})"
                for nom, qui in sorted(manquants.items())]
    return defauts
