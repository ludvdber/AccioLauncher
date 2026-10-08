"""Installer d'un seul clic les composants Windows qui manquent (ACT-054).

Sous Windows, chaque composant manquant s'installait à la main, un à la fois,
depuis une page Microsoft en anglais ; la saga en demande jusqu'à cinq. Sous
Linux, le launcher les installait déjà lui-même (`preparation_wine`). Ici, le
pendant Windows :

1. chaque installeur est téléchargé chez Microsoft — rien n'est redistribué ;
2. sa signature Authenticode est vérifiée : valide, et au nom de « Microsoft
   Corporation ». Un fichier qui ne passe pas n'est JAMAIS exécuté ;
3. tous s'exécutent en mode silencieux, depuis UN script lancé derrière UNE
   invite administrateur, annoncée avant (règle 69) ;
4. la RELECTURE fait foi : on refait les tests de `system_checks` ; le code de
   sortie d'un installeur ne dit pas si le jeu trouvera sa DLL.

Adresses et options relevées le 2026-10-07 : les cinq fichiers téléchargés
portaient une signature valide de Microsoft Corporation. Les options
silencieuses sont celles que documente Microsoft pour chaque famille ; elles
n'ont pas encore été vues sur un Windows où ces composants manquent.

Rien ne se voit ici : le fil exécute et émet ; `ui/installateur_composants.py`
dit ce qui s'affiche.
"""

import base64
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.core import system_checks
from src.core.formatting import format_bytes
from src.core.i18n import tr

log = logging.getLogger(__name__)

# Raisons d'échec émises avec `installation_terminee` (vide = réussie).
ANNULEE = "annulee"
TELECHARGEMENT = "telechargement"
SIGNATURE = "signature"
REFUSEE = "refusee"          # l'invite administrateur a été refusée
COMPOSANTS = "composants"    # installés, mais la relecture en trouve encore un absent

# Règle 6 : la constante n'existe que sous Windows, nommée ici sous garde.
_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


@dataclass(frozen=True, slots=True)
class Paquet:
    """Un installeur Microsoft, et comment le faire taire."""

    cle: str            # nom du fichier posé, et clé du résultat
    nom: str            # nom de produit, non traduit
    url: str
    arguments: str      # options silencieuses
    taille_mo: int      # poids de l'installeur, pour l'annoncer avant


# Ordre d'installation : les plus anciens d'abord, DirectX en dernier.
PAQUETS = {
    "vc2005": Paquet("vc2005", "Visual C++ 2005",
                     "https://download.microsoft.com/download/8/B/4/"
                     "8B42259F-5D70-43F4-AC2E-4B208FD8D66A/vcredist_x86.EXE", "/q", 3),
    "vc2008": Paquet("vc2008", "Visual C++ 2008",
                     "https://download.microsoft.com/download/5/D/8/"
                     "5D8C65CB-C849-4025-8E95-C3966CAFD8AE/vcredist_x86.exe", "/q", 5),
    "vc2010": Paquet("vc2010", "Visual C++ 2010",
                     "https://download.microsoft.com/download/1/6/5/"
                     "165255E7-1014-4D0A-B094-B6A430A6BFFC/vcredist_x86.exe", "/q /norestart", 9),
    "vc2022": Paquet("vc2022", "Visual C++ 2015-2022", system_checks.VCREDIST_URL,
                     "/install /quiet /norestart", 14),
    # L'installeur web : il ne télécharge que ce qui manque du runtime de juin 2010.
    "directx": Paquet("directx", "DirectX",
                      "https://download.microsoft.com/download/1/7/1/"
                      "1718CCC4-6315-4D8E-9543-8E28A4E18C4C/dxwebsetup.exe", "/Q", 1),
}

# Identifiant de prérequis du catalogue → paquet qui le fournit.
PAQUET_DU_PREREQUIS = {
    "vcredist_x86": "vc2022",
    "vcredist2005_x86": "vc2005",
    "vcredist2008_x86": "vc2008",
    "vcredist2010_x86": "vc2010",
    **{nom: "directx" for nom in system_checks.DLL_DIRECTX9},
    **{nom: "directx" for nom in system_checks.DLL_COMPILATEUR},
}


def paquets_pour(manquants) -> list[Paquet]:
    """Les installeurs qui couvrent ces prérequis, une fois chacun, dans l'ordre
    de `PAQUETS`. Un identifiant inconnu est ignoré. Pure."""
    voulus = {PAQUET_DU_PREREQUIS[m] for m in manquants if m in PAQUET_DU_PREREQUIS}
    return [p for cle, p in PAQUETS.items() if cle in voulus]


def disponible() -> bool:
    """L'installation en un clic n'existe que sous Windows (Linux : winetricks)."""
    return sys.platform == "win32"


# ──────────────────── Script élevé ────────────────────

FICHIER_RESULTATS = "resultats.txt"


def script_d_installation(paquets) -> str:
    """Corps du `.bat` qui installe tout, d'une traite, derrière UNE invite. Pure.

    AUCUN chemin dans le corps (règle 79) : les installeurs sont à côté du
    script, atteints par `%~dp0`, que cmd développe lui-même en Unicode. Un
    chemin écrit ici serait relu en page OEM, et un dossier temporaire sous
    « C:\\Users\\Frédéric » ne serait plus trouvé. Le résultat de chaque
    installeur est noté, la redirection EN TÊTE de ligne : `echo x 0>>f`
    redirigerait le flux 0 au lieu d'écrire le code.
    """
    lignes = ["@echo off", "setlocal", 'cd /d "%~dp0"']
    for p in paquets:
        lignes.append(f'start "" /wait "%~dp0{p.cle}.exe" {p.arguments}')
        lignes.append(f'>>"%~dp0{FICHIER_RESULTATS}" echo {p.cle} %errorlevel%')
    lignes.append("exit /b 0")
    return "\r\n".join(lignes) + "\r\n"


def lire_resultats(texte: str) -> dict[str, int]:
    """« vc2005 0 » ligne par ligne → {"vc2005": 0}. Pure ; ignore le reste."""
    resultats = {}
    for ligne in texte.splitlines():
        morceaux = ligne.split()
        if len(morceaux) == 2 and morceaux[0] in PAQUETS:
            try:
                resultats[morceaux[0]] = int(morceaux[1])
            except ValueError:
                continue
    return resultats


# ──────────────────── Signature ────────────────────

# Le chemin passe par l'ENVIRONNEMENT, jamais dans le texte de la commande :
# rien de ce qu'on vérifie ne peut s'y glisser comme code.
_SCRIPT_SIGNATURE = (
    "$s = Get-AuthenticodeSignature -LiteralPath $env:ACCIO_FICHIER; "
    "[Console]::Out.Write([string]$s.Status + '|' + [string]$s.SignerCertificate.Subject)")


def est_signe_par_microsoft(statut: str, sujet: str) -> bool:
    """Signature valide ET au nom de Microsoft Corporation. Pure.

    `Valid` dit que la chaîne remonte à une racine de confiance et que le
    fichier n'a pas bougé depuis la signature ; le sujet dit QUI a signé.
    """
    if statut.strip() != "Valid":
        return False
    champs = {c.strip() for c in sujet.split(",")}
    return "O=Microsoft Corporation" in champs and "CN=Microsoft Corporation" in champs


def signature_microsoft(fichier: Path) -> bool:
    """Lit la signature Authenticode du fichier (Windows) ; False au moindre doute."""
    if sys.platform != "win32":
        return False
    from src.core.win_utils import dossier_systeme

    powershell = Path(dossier_systeme()) / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    commande = base64.b64encode(_SCRIPT_SIGNATURE.encode("utf-16-le")).decode("ascii")
    env = {**os.environ, "ACCIO_FICHIER": str(fichier)}
    try:
        sortie = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand", commande],
            capture_output=True, timeout=60, env=env, creationflags=_SANS_FENETRE)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Signature de %s illisible : %s", fichier.name, exc)
        return False
    texte = sortie.stdout.decode("utf-8", "replace")
    statut, _, sujet = texte.partition("|")
    ok = est_signe_par_microsoft(statut, sujet)
    log.info("Signature de %s : %s (%s)", fichier.name, statut or "?", sujet or "aucun signataire")
    return ok


# ──────────────────── Élévation ────────────────────

_ERREUR_ANNULEE = 1223   # ERROR_CANCELLED : l'invite UAC a été refusée


ABANDON = -1   # le launcher se ferme : on cesse d'attendre les installeurs


def executer_eleve(script: Path, abandonner=lambda: False) -> int | None:
    """Exécute le script derrière une invite administrateur et ATTEND sa fin.

    None : l'invite a été refusée (ou l'élévation est impossible). `ABANDON` :
    `abandonner()` est devenu vrai pendant l'attente — les installeurs de
    Microsoft vont au bout sans nous, on ne coupe pas un MSI. Sinon, le
    code de sortie de cmd. `cmd.exe` par son chemin ABSOLU (règle 1) : nommé
    seul, il serait cherché d'abord dans le dossier courant, et lancé élevé.
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    from src.core.win_utils import commande_systeme

    class _Info(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]

    see_mask_nocloseprocess, see_mask_noasync = 0x40, 0x100
    info = _Info()
    info.cbSize = ctypes.sizeof(_Info)
    info.fMask = see_mask_nocloseprocess | see_mask_noasync
    info.lpVerb = "runas"
    info.lpFile = commande_systeme("cmd.exe")
    info.lpParameters = f'/d /c ""{script}""'
    info.lpDirectory = str(script.parent)
    info.nShow = 0
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_Info)]
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        erreur = ctypes.get_last_error()
        log.info("Élévation %s (erreur %d)",
                 "refusée" if erreur == _ERREUR_ANNULEE else "impossible", erreur)
        return None
    if not info.hProcess:
        return None
    try:
        wait_timeout = 0x102
        while kernel32.WaitForSingleObject(wintypes.HANDLE(info.hProcess), 500) == wait_timeout:
            if abandonner():
                return ABANDON
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(wintypes.HANDLE(info.hProcess), ctypes.byref(code))
        return int(code.value)
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(info.hProcess))


# ──────────────────── Le fil ────────────────────

_TRANCHE = 64 * 1024
_ECART_AVANCEMENT_S = 0.25


class InstallationComposants(QThread):
    """Télécharge, vérifie, puis installe d'une traite les composants demandés."""

    # (« telechargement » | « installation », noms séparés par « , »)
    etape = pyqtSignal(str, str)
    # Une ligne lisible : « Visual C++ 2005 : 1,2 Mo sur 2,6 Mo ».
    avancement = pyqtSignal(str)
    # (réussie, raison) — nommé, jamais `finished` (règle 7)
    installation_terminee = pyqtSignal(bool, str)

    def __init__(self, prerequis, parent=None) -> None:
        super().__init__(parent)
        self._prerequis = tuple(prerequis)
        self._paquets = paquets_pour(self._prerequis)

    def annuler(self) -> None:
        """Arrête les téléchargements. Une fois l'invite acceptée, les
        installeurs de Microsoft vont au bout : on ne coupe pas un MSI."""
        self.requestInterruption()

    def run(self) -> None:
        dossier = Path(tempfile.mkdtemp(prefix="accio_composants_"))
        try:
            reussie, raison = self._installer(dossier)
        except (OSError, ValueError) as exc:
            log.warning("Installation des composants interrompue : %s", exc)
            reussie, raison = False, TELECHARGEMENT
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        log.info("Composants Windows : %s%s", "installés" if reussie else "échec",
                 f" ({raison})" if raison else "")
        self.installation_terminee.emit(reussie, raison)

    def _installer(self, dossier: Path) -> tuple[bool, str]:
        # Dossier à nom ALÉATOIRE (règle 70) : ce qu'il contient sera exécuté
        # en administrateur, et un nom prévisible laisserait un programme sans
        # privilège y glisser le sien entre la vérification et l'exécution.
        self.etape.emit("telechargement", ", ".join(p.nom for p in self._paquets))
        for paquet in self._paquets:
            fichier = dossier / f"{paquet.cle}.exe"
            if not self._telecharger(paquet, fichier):
                return False, ANNULEE if self.isInterruptionRequested() else TELECHARGEMENT
            if not signature_microsoft(fichier):
                log.warning("%s : signature refusée, rien n'est exécuté", paquet.nom)
                return False, SIGNATURE
        if self.isInterruptionRequested():
            return False, ANNULEE
        script = dossier / "installer.bat"
        script.write_bytes(script_d_installation(self._paquets).encode("ascii", "strict"))
        self.etape.emit("installation", ", ".join(p.nom for p in self._paquets))
        code = executer_eleve(script, self.isInterruptionRequested)
        if code is None:
            return False, REFUSEE
        if code == ABANDON:
            return False, ANNULEE
        try:
            resultats = lire_resultats(
                (dossier / FICHIER_RESULTATS).read_text(encoding="ascii", errors="replace"))
        except OSError:
            resultats = {}
        log.info("Codes des installeurs : %s", resultats or "aucun relevé")
        # La relecture fait foi, pas les codes (3010, 1638… ne disent pas tout).
        system_checks.invalidate_vcredist_cache()
        restants = system_checks.prerequis_manquants(self._prerequis)
        if restants:
            log.warning("Toujours absents après installation : %s", ", ".join(restants))
            return False, COMPOSANTS
        return True, ""

    def _telecharger(self, paquet: Paquet, fichier: Path) -> bool:
        import httpx

        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0)) as client:
                with client.stream("GET", paquet.url) as reponse:
                    reponse.raise_for_status()
                    total = int(reponse.headers.get("Content-Length") or 0)
                    recu, dernier = 0, 0.0
                    with open(fichier, "wb") as sortie:
                        for morceau in reponse.iter_bytes(_TRANCHE):
                            if self.isInterruptionRequested():
                                return False
                            sortie.write(morceau)
                            recu += len(morceau)
                            maintenant = time.monotonic()
                            if maintenant - dernier >= _ECART_AVANCEMENT_S:
                                dernier = maintenant
                                self.avancement.emit(_ligne(paquet.nom, recu, total))
        except (httpx.HTTPError, OSError) as exc:
            log.warning("%s : téléchargement impossible (%s)", paquet.nom, exc)
            return False
        self.avancement.emit(_ligne(paquet.nom, recu, total or recu))
        return True


def _ligne(nom: str, recu: int, total: int) -> str:
    """« Visual C++ 2005 : 1,2 Mo sur 2,6 Mo », dans la langue de l'interface."""
    if total:
        return tr("{} : {} sur {}").format(nom, format_bytes(recu), format_bytes(total))
    return tr("{} : {}").format(nom, format_bytes(recu))
