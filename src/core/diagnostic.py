"""Informations de diagnostic — ce qu'il faut pour dépanner quelqu'un à distance.

Né de l'audit du 2026-09-18. Le launcher circule de main en main et l'aide
passe par le Discord : la première question y est toujours la même (« quelle
version, quel Windows, quel jeu ? ») et la personne ne sait pas y répondre.
Deux défauts le rendaient pénible :

- le JOURNAL ne portait ni la version du launcher ni celle de Windows — hors
  ligne, la version n'y apparaissait jamais, puisqu'elle n'était écrite que par
  la vérification des mises à jour ;
- rien ne permettait de COPIER ces informations : il fallait les dicter.

Ce module est pur (aucun widget) : il lit la plateforme, le catalogue, les
stats et le journal, et rend du texte. L'interface se contente de le copier.

Rien de personnel n'en sort : le dossier personnel est remplacé par « ~ »
(`scrub_user_paths`), qui cachait déjà le nom d'utilisateur dans le rapport de
plantage.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import sys
from pathlib import Path

from src.core.config import APP_VERSION, get_documents_dir

log = logging.getLogger(__name__)

# Lignes du journal reprises dans le diagnostic : les AVERTISSEMENTS et les
# ERREURS seulement. Le reste raconte le fonctionnement normal, et un
# diagnostic de plus de 2 000 caractères devient une pièce jointe sur Discord.
_LIGNES_NOTABLES = 12
_TENTATIVES = 5


def scrub_user_paths(text: str) -> str:
    """Remplace le dossier personnel par ~ (ne pas exposer le nom d'utilisateur)."""
    home = str(Path.home())
    for variant in (home, home.replace("\\", "/"), home.replace("\\", "\\\\")):
        text = text.replace(variant, "~")
    if sys.platform != "win32":
        text = _sans_profil_wine(text)
    return text


def _sans_profil_wine(text: str) -> str:
    """Le profil d'un préfixe Wine porte le nom UNIX (`drive_c/users/ludo`,
    `C:\\users\\ludo`) : remplacer le dossier personnel ne le cache pas."""
    from src.core.compat import PROFIL_PROTON, _nom_unix
    nom = _nom_unix()
    if not nom or nom == PROFIL_PROTON:
        return text
    return re.sub(r"(users(?:/|\\{1,2}))" + re.escape(nom) + r"(?![\w.-])", r"\1~",
                  text, flags=re.IGNORECASE)


def systeme() -> str:
    """« Windows 11 Professional 10.0.26200 (AMD64) », ou l'équivalent ailleurs."""
    if sys.platform == "win32":
        release, version, _, _ = platform.win32_ver()
        edition = platform.win32_edition() or ""
        nom = " ".join(x for x in ("Windows", release, edition, version) if x)
    elif sys.platform.startswith("linux"):
        # « Linux 6.15.9 » ne dit ni la distribution ni la session : sur
        # Bazzite, le mode Jeu (Gamescope) et le bureau (KDE, Wayland) ne se
        # dépannent pas de la même façon.
        try:
            os_release = platform.freedesktop_os_release()
        except OSError:
            os_release = {}
        nom = f"{distribution(os_release)} · noyau {platform.release()}"
        session = session_graphique(os.environ)
        return f"{nom} ({platform.machine()})" + (f" · {session}" if session else "")
    else:
        nom = f"{platform.system()} {platform.release()}"
    return f"{nom} ({platform.machine()})"


def distribution(os_release: dict) -> str:
    """« Bazzite 42 (FROM Fedora Kinoite) » — le nom que la personne connaît."""
    nom = os_release.get("PRETTY_NAME") or " ".join(
        x for x in (os_release.get("NAME", ""), os_release.get("VERSION_ID", "")) if x)
    return " ".join(nom.split()) or "Linux"


def session_graphique(env) -> str:
    """« KDE · Wayland », « Gamescope » (mode Jeu de Bazzite / Steam Deck)."""
    if env.get("GAMESCOPE_WAYLAND_DISPLAY") or "gamescope" in env.get(
            "XDG_CURRENT_DESKTOP", "").lower():
        return "Gamescope"
    bureau = env.get("XDG_CURRENT_DESKTOP", "").split(":")[0].strip()
    type_ = {"wayland": "Wayland", "x11": "X11"}.get(env.get("XDG_SESSION_TYPE", "").lower(), "")
    return " · ".join(x for x in (bureau, type_) if x)


def identite() -> str:
    """Une ligne : version, forme (exe ou sources), système, Python, Qt."""
    try:
        from PyQt6.QtCore import qVersion
        qt = f" · Qt {qVersion()}"
    except ImportError:
        qt = ""
    forme = "exe" if getattr(sys, "frozen", False) else "sources"
    if forme == "exe" and sys.platform != "win32" and os.environ.get("APPIMAGE"):
        forme = "AppImage"
    return (f"Accio Launcher {APP_VERSION} ({forme}) · {systeme()}"
            f" · Python {platform.python_version()}{qt}")


def ecran(largeur: int, hauteur: int, echelle: float) -> str:
    """« 2560×1440 à 125 % » — en pixels PHYSIQUES : Qt donne des pixels
    logiques (2048×1152 pour le même écran), qu'on ne reconnaît pas."""
    return f"{round(largeur * echelle)}×{round(hauteur * echelle)} à {round(echelle * 100)} %"


# Classe des adaptateurs d'affichage dans le registre (GUID fixe de Windows).
_CLE_AFFICHAGE = (r"SYSTEM\CurrentControlSet\Control\Class"
                  r"\{4d36e968-e325-11ce-bfc1-08002be10318}")


def version_pilote_publique(fournisseur: str, version: str, radeon: str = "") -> str:
    """Le numéro que l'utilisateur RECONNAÎT, pas celui de Windows.

    Windows range « 32.0.16.1074 » là où NVIDIA affiche « 610.74 » : ce sont
    les cinq derniers chiffres des deux derniers blocs. AMD range son numéro
    public (« 25.8.1 ») dans une valeur à part. Intel affiche le numéro Windows
    tel quel. Demander « quelle version de pilote ? » à quelqu'un qui lit
    610.74 dans son panneau NVIDIA et voir 32.0.16.1074 ici, c'est deux
    réponses qu'on ne sait pas raccorder.
    """
    fournisseur = fournisseur.lower()
    if "nvidia" in fournisseur:
        blocs = version.split(".")
        if len(blocs) == 4 and all(b.isdigit() for b in blocs[2:]):
            chiffres = (blocs[2] + blocs[3].zfill(4))[-5:]
            return f"{chiffres[:3]}.{chiffres[3:]}"
    if radeon and ("amd" in fournisseur or "ati" in fournisseur):
        return radeon
    return version


def _processeur() -> str:
    """Nom commercial du processeur et nombre de cœurs logiques."""
    nom = ""
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as cle:
                nom = str(winreg.QueryValueEx(cle, "ProcessorNameString")[0])
        except OSError:
            pass
    elif sys.platform.startswith("linux"):
        # `platform.processor()` y rend « x86_64 », ou rien.
        nom = processeur_linux(_lire_texte(Path("/proc/cpuinfo")))
    nom = " ".join((nom or platform.processor() or "inconnu").split())
    return f"{nom} ({os.cpu_count() or '?'} threads)"


def processeur_linux(cpuinfo: str) -> str:
    """Le « model name » de `/proc/cpuinfo` (vide sur ARM, qui ne le porte pas)."""
    for ligne in cpuinfo.splitlines():
        cle, _, valeur = ligne.partition(":")
        if cle.strip() == "model name" and valeur.strip():
            return valeur.strip()
    return ""


def _lire_texte(chemin: Path) -> str:
    try:
        return chemin.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _memoire() -> str:
    """Mémoire vive totale, en Go ; vide si le système ne la dit pas."""
    if sys.platform != "win32":
        try:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (AttributeError, ValueError, OSError):
            return ""
        return f"{total / 1024 ** 3:.0f} Go" if total > 0 else ""
    import ctypes

    class _Etat(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    etat = _Etat()
    etat.dwLength = ctypes.sizeof(_Etat)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(etat)):
            return ""
    except (AttributeError, OSError):
        return ""
    return f"{etat.ullTotalPhys / 1024 ** 3:.0f} Go"


def _cartes_graphiques() -> list[str]:
    """Une ligne par adaptateur d'affichage : nom, pilote, date, mémoire.

    Lu dans le REGISTRE, en lecture seule, et non par `wmic` (retiré de
    Windows 11 24H2) ni PowerShell (une seconde de démarrage pour trois
    valeurs). Les adaptateurs virtuels (Parsec, écran distant…) sont gardés et
    signalés : ils sont justement une cause classique de plein écran raté.
    """
    if sys.platform.startswith("linux"):
        return cartes_graphiques_linux()
    if sys.platform != "win32":
        return []
    import winreg
    cartes = []
    try:
        classe = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CLE_AFFICHAGE)
    except OSError:
        return []
    with classe:
        i = 0
        while i < 32:
            try:
                sous = winreg.EnumKey(classe, i)
            except OSError:
                break
            i += 1
            if not sous.isdigit():
                continue
            valeurs = {}
            try:
                with winreg.OpenKey(classe, sous) as cle:
                    for nom in ("DriverDesc", "DriverVersion", "DriverDate", "ProviderName",
                                "RadeonSoftwareVersion", "MatchingDeviceId",
                                "HardwareInformation.qwMemorySize"):
                        try:
                            valeurs[nom] = winreg.QueryValueEx(cle, nom)[0]
                        except OSError:
                            pass
            except OSError:
                continue
            if not valeurs.get("DriverDesc"):
                continue
            cartes.append(carte_graphique(valeurs))
    return cartes


def carte_graphique(v: dict) -> str:
    """Met en forme une entrée du registre (pure, testable hors Windows)."""
    fournisseur = f"{v.get('ProviderName', '')} {v.get('DriverDesc', '')}"
    version = version_pilote_publique(fournisseur, str(v.get("DriverVersion", "?")),
                                      str(v.get("RadeonSoftwareVersion", "") or ""))
    morceaux = [str(v["DriverDesc"]).strip(), f"pilote {version}"]
    if v.get("DriverDate"):
        # Windows l'écrit à l'américaine (« 7-2-2026 » = 2 juillet) : lu en
        # Europe, c'est le 7 février. ISO, que personne ne lit de travers.
        m, _, reste = str(v["DriverDate"]).partition("-")
        j, _, a = reste.partition("-")
        date = (f"{a}-{int(m):02d}-{int(j):02d}"
                if m.isdigit() and j.isdigit() and a.isdigit() else str(v["DriverDate"]))
        morceaux.append(f"du {date}")
    memoire = v.get("HardwareInformation.qwMemorySize")
    if isinstance(memoire, int) and memoire > 0:
        morceaux.append(f"{memoire / 1024 ** 3:.0f} Go")
    if not str(v.get("MatchingDeviceId", "")).lower().startswith("pci"):
        morceaux.append("virtuel")
    return " · ".join(morceaux)


# Base des noms PCI : `hwdata` (Fedora, donc Bazzite), `pciutils` (Debian).
_PCI_IDS = (Path("/usr/share/hwdata/pci.ids"), Path("/usr/share/misc/pci.ids"),
            Path("/usr/share/pci.ids"))


def cartes_graphiques_linux(drm: Path = Path("/sys/class/drm"),
                            bases=_PCI_IDS,
                            nvidia: Path = Path("/proc/driver/nvidia/version")) -> list[str]:
    """Une ligne par carte vue par le noyau (`/sys/class/drm/cardN`).

    Aucun programme lancé (ni `lspci` ni `glxinfo`, absents d'une image
    atomique ou lents) : le noyau dit le pilote et l'identifiant PCI, la base
    `pci.ids` le nom. La version du pilote NVIDIA propriétaire se lit dans
    `/proc` ; celle de Mesa n'existe qu'en espace utilisateur, on ne la devine
    pas.
    """
    try:
        cartes = sorted(d for d in drm.iterdir() if re.fullmatch(r"card\d+", d.name))
    except OSError:
        return []
    base: str | None = None      # lue au premier besoin, une seule fois (1,4 Mo)
    lignes = []
    for carte in cartes:
        uevent = _lire_texte(carte / "device" / "uevent")
        if not uevent:
            continue
        if base is None:
            base = next((t for t in map(_lire_texte, bases) if t), "")
        vram = _lire_texte(carte / "device" / "mem_info_vram_total").strip()
        lignes.append(carte_graphique_linux(
            uevent, base, int(vram) if vram.isdigit() else 0, _lire_texte(nvidia)))
    return lignes


def carte_graphique_linux(uevent: str, pci_ids: str = "", vram: int = 0,
                          version_nvidia: str = "") -> str:
    """Met en forme une carte (pure) : nom, pilote du noyau, version, mémoire."""
    champs = dict(ligne.partition("=")[::2] for ligne in uevent.splitlines() if "=" in ligne)
    fabricant, _, modele = champs.get("PCI_ID", "").lower().partition(":")
    pilote = champs.get("DRIVER", "") or "sans pilote"
    nom = nom_pci(fabricant, modele, pci_ids) or (
        f"PCI {fabricant}:{modele}" if modele else "carte inconnue")
    morceaux = [nom, f"pilote {pilote}"]
    if pilote == "nvidia":
        m = re.search(r"Kernel Module(?:\s+for\s+\S+)?\s+(\d+(?:\.\d+)+)", version_nvidia)
        if m:
            morceaux[-1] += f" {m.group(1)}"
    if vram > 0:
        morceaux.append(f"{vram / 1024 ** 3:.0f} Go")
    return " · ".join(morceaux)


def nom_pci(fabricant: str, modele: str, pci_ids: str) -> str:
    """« AMD · Navi 21 [Radeon RX 6800/6800 XT / 6900 XT] » d'après `pci.ids`.

    Le fabricant est abrégé à ce qu'on reconnaît (les noms complets
    ressemblent à « Advanced Micro Devices, Inc. [AMD/ATI] »).
    """
    if not (fabricant and modele and pci_ids):
        return ""
    nom_fabricant = ""
    dans_le_fabricant = False
    for ligne in pci_ids.splitlines():
        if not ligne or ligne.startswith("#"):
            continue
        if not ligne.startswith("\t"):
            if dans_le_fabricant:
                break
            code, _, nom = ligne.partition(" ")
            if code.lower() == fabricant:
                dans_le_fabricant, nom_fabricant = True, nom.strip()
        elif dans_le_fabricant and not ligne.startswith("\t\t"):
            code, _, nom = ligne[1:].partition(" ")
            if code.lower() == modele:
                return f"{_FABRICANTS.get(fabricant, nom_fabricant)} · {nom.strip()}"
    return f"{_FABRICANTS.get(fabricant, nom_fabricant)} · {modele}" if nom_fabricant else ""


_FABRICANTS = {"1002": "AMD", "10de": "NVIDIA", "8086": "Intel"}


def ligne_compatibilite(trouve=None, pfx: Path | None = None) -> str:
    """Le lanceur, le Proton choisi et l'état du préfixe (Linux).

    Sous Linux, ce sont les réponses à « ça ne se lance pas » : quel lanceur,
    quel Proton, le préfixe existe-t-il, qu'y a-t-on installé.
    """
    from src.core import compat
    trouve = compat.lanceur() if trouve is None else trouve
    if trouve is None:
        return "Compatibilité : aucun lanceur trouvé (ni umu-run ni wine)"
    morceaux = [f"{Path(trouve.executable).name} ({trouve.executable})"]
    if trouve.proton:
        morceaux.append(Path(trouve.proton).name)
    if trouve.famille == "wine":
        morceaux.append("winetricks " + ("présent" if trouve.winetricks else "ABSENT"))
    pfx = compat.prefixe(trouve.famille) if pfx is None else pfx
    if compat.pret(pfx):
        etat = f"préfixe {pfx} prêt ({compat.architecture(pfx) or '?'}"
        etat += f", {compat.encodage_ansi(pfx)})"
        verbes = sorted(compat.verbes_installes(pfx))
        morceaux.append(etat)
        morceaux.append("composants " + (", ".join(verbes) if verbes else "aucun"))
    else:
        morceaux.append(f"préfixe {pfx} PAS ENCORE CRÉÉ")
    return "Compatibilité : " + " · ".join(morceaux)


def materiel() -> list[str]:
    """Processeur, mémoire et cartes graphiques : ce qu'on demande d'abord
    devant un écran noir ou un jeu qui ne passe pas en plein écran."""
    lignes = []
    memoire = _memoire()
    lignes.append(f"Processeur : {_processeur()}" + (f" · {memoire} de mémoire" if memoire else ""))
    cartes = _cartes_graphiques()
    if cartes:
        lignes.append("Carte graphique : " + cartes[0] if len(cartes) == 1
                      else "Cartes graphiques :")
        if len(cartes) > 1:
            lignes += [f"  {c}" for c in cartes]
    return lignes


def lignes_notables(journal: str, n: int = _LIGNES_NOTABLES) -> list[str]:
    """Les `n` derniers avertissements et erreurs d'un journal."""
    marques = ("WARNING:", "ERROR:", "CRITICAL:")
    return [ligne for ligne in journal.splitlines()
            if any(m in ligne for m in marques)][-n:]


def _espace_libre(dossier: Path) -> str:
    chemin = dossier
    while not chemin.exists() and chemin != chemin.parent:
        chemin = chemin.parent
    try:
        return f"{shutil.disk_usage(chemin).free / 1024 ** 3:.0f} Go libres"
    except OSError:
        return "espace libre inconnu"


def rapport(manager, ecrans: list[str] | None = None, journal: str = "",
            tentatives=None, prerequis: dict[str, bool] | None = None,
            machine: list[str] | None = None, documents: str | None = None,
            compatibilite: str | None = None) -> str:
    """Le bloc à coller sur le Discord.

    `tentatives`, `prerequis`, `machine` et `compatibilite` sont injectables
    pour les tests ; par défaut ils sont lus (journal des sessions, contrôles
    système mis en cache, registre en lecture seule, préfixe Wine).
    """
    config = manager.config
    lignes = [identite()]
    langue = getattr(config, "langue", "?")
    lignes.append(f"Interface : {langue} · thème {getattr(config, 'theme', '?')}"
                  f" · catalogue v{manager.catalog.catalog_version}")
    try:
        lignes += materiel() if machine is None else machine
    except Exception as exc:  # un registre inattendu ne doit pas priver du reste
        log.warning("Matériel illisible pour le diagnostic : %s", exc)
    if ecrans:
        lignes.append("Écrans : " + " ; ".join(ecrans))
    lignes.append(f"Dossier des jeux : {config.install_path} — "
                  f"{_espace_libre(Path(config.install_path))}")
    # Documents est le seul autre endroit où des jeux écrivent (HP1, HP2, HP3).
    # Chez l'utilisateur du 2026-09-20 il était inaccessible, et il a fallu le
    # DÉDUIRE d'un avertissement du journal : cette ligne donne la réponse.
    if documents is None:
        from src.core.pre_launch import documents_inutilisable
        casse = documents_inutilisable() is not None
        documents = f"{get_documents_dir()}" + (" — INACCESSIBLE" if casse else "")
    lignes.append(f"Documents : {documents}")

    if compatibilite is None and sys.platform != "win32":
        try:
            compatibilite = ligne_compatibilite()
        except Exception as exc:  # un préfixe inattendu ne doit pas priver du reste
            log.warning("Préfixe illisible pour le diagnostic : %s", exc)
    if compatibilite:
        lignes.append(compatibilite)

    if prerequis is None:
        from src.core.system_checks import PREREQUIS, check_d3d11_feature_level
        prerequis = {nom: bool(test()) for nom, (test, _) in PREREQUIS.items()}
        # Hors Windows, `check_d3d11_feature_level` répond oui sans avoir rien
        # mesuré (DXVK s'en charge) : l'écrire « OK » affirmerait un résultat
        # qu'on n'a pas obtenu.
        if sys.platform == "win32":
            prerequis["directx11"] = bool(check_d3d11_feature_level())
    lignes.append("Prérequis : " + ", ".join(
        f"{nom} {'OK' if ok else 'MANQUANT'}" for nom, ok in prerequis.items()))

    from src.core.game_manager import GameState

    installes = []
    for g in manager.catalog.games:
        etat = manager.get_state(g.id)
        if etat == GameState.NOT_INSTALLED:
            continue
        version = manager.installed_version(g.id) or "?"
        minutes = manager.get_playtime(g.id) // 60
        installes.append(f"  {g.id} v{version} — {etat} — {minutes} min de jeu")
    lignes.append("Jeux installés :" if installes else "Jeux installés : aucun")
    lignes += installes

    if tentatives is None:
        try:
            from src.core import stats
            tentatives = stats.charger().tentatives
        except Exception:  # un journal illisible ne doit pas priver du reste
            tentatives = ()
    recentes = sorted(tentatives, key=lambda t: t.debut)[-_TENTATIVES:]
    if recentes:
        lignes.append("Lancements qui n'ont pas démarré :")
        lignes += [f"  {t.jeu} le {t.debut:%Y-%m-%d %H:%M} — {t.duree} s, code {t.code}"
                   for t in recentes]

    notables = lignes_notables(journal)
    if notables:
        lignes.append(f"── Journal : {len(notables)} derniers avertissements ──")
        lignes += notables
    return scrub_user_paths("\n".join(lignes))
