"""Préparer le préfixe Wine : le créer, puis y installer les composants.

Sous Linux, un jeu ne démarre qu'une fois son « Windows » prêt : le préfixe
partagé (`compat.prefixe()`) doit exister, et les runtimes Visual C++ que le
catalogue exige doivent y être installés — par winetricks, qui les télécharge
depuis Microsoft. C'est l'équivalent de la page de téléchargement qu'ouvre la
version Windows, mais fait POUR l'utilisateur, dans un préfixe qu'il ne voit
pas.

Pourquoi un fil à part, et pas dans `launch_game` : la toute première fois,
umu télécharge aussi Proton et le Steam Linux Runtime (plusieurs centaines de
Mo). Rien de tout ça ne peut tenir la fenêtre figée. `launch_game` refuse donc
de partir tant que la préparation manque, et l'interface la propose — sur un
clic, jamais d'elle-même.

Rien ne se voit ici : le fil exécute et émet ; `ui/preparateur_wine.py` décide
de ce qui s'affiche.
"""

import logging
import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.core import compat

log = logging.getLogger(__name__)

# Raisons d'échec émises avec `preparation_terminee` (vide = réussie).
ANNULEE = "annulee"
PREFIXE = "prefixe"
WINETRICKS_ABSENT = "winetricks_absent"
COMPOSANTS = "composants"

# Attente de `system.reg` après la création : Wine ne l'écrit qu'à l'arrêt de
# son serveur, quelques secondes après la fin de `wineboot` (cf. docs/LINUX.md).
_ATTENTE_PREFIXE_S = 90
_ATTENTE_APRES_ERREUR_S = 10
_PAS_S = 0.5
_ARRET_S = 3


class PreparationWine(QThread):
    """Crée le préfixe s'il manque, puis installe les verbes winetricks demandés."""

    # (« prefixe » | « composants », verbes séparés par des espaces)
    etape = pyqtSignal(str, str)
    # (réussie, raison) — nommé, jamais `finished` (cf. QThread)
    preparation_terminee = pyqtSignal(bool, str)

    def __init__(self, lanceur: compat.Lanceur, prefixe: Path, verbes,
                 journal: Path, parent=None) -> None:
        super().__init__(parent)
        self._lanceur = lanceur
        self._prefixe = prefixe
        self._verbes = tuple(verbes)
        self._journal = journal

    @property
    def journal(self) -> Path:
        return self._journal

    def annuler(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        try:
            reussie, raison = self._preparer()
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            log.warning("Préparation de Wine interrompue : %s", exc)
            reussie, raison = False, PREFIXE if not compat.pret(self._prefixe) else COMPOSANTS
        log.info("Préparation de Wine : %s%s", "réussie" if reussie else "échec",
                 f" ({raison})" if raison else "")
        self.preparation_terminee.emit(reussie, raison)

    # ──────────────────── Étapes ────────────────────

    def _preparer(self) -> tuple[bool, str]:
        self._journal.parent.mkdir(parents=True, exist_ok=True)
        self._journal.write_bytes(b"")
        if not compat.pret(self._prefixe):
            self.etape.emit("prefixe", "")
            self._prefixe.mkdir(parents=True, exist_ok=True)
            env = compat.environnement(self._lanceur, self._prefixe)
            if self._lanceur.famille == "wine":
                # Wine propose d'installer Mono et Gecko à la création d'un
                # préfixe, par des fenêtres que personne n'attend ici ; aucun
                # des huit jeux n'en a besoin.
                env["WINEDLLOVERRIDES"] = ";".join(
                    m for m in (env.get("WINEDLLOVERRIDES", ""), "mscoree,mshtml=") if m)
            code = self._executer(compat.commande_creation(self._lanceur), env)
            if code is None:
                return False, ANNULEE
            # Un code non nul ne prouve pas l'échec — `umu-run ""` en rend un
            # une fois le préfixe créé, faute d'exécutable à lancer (commentaire
            # d'umu lui-même) — mais il ne justifie pas non plus d'attendre une
            # minute et demie un fichier qui ne viendra pas.
            delai = _ATTENTE_PREFIXE_S if code == 0 else _ATTENTE_APRES_ERREUR_S
            if not self._attendre(lambda: compat.pret(self._prefixe), delai):
                return False, ANNULEE if self.isInterruptionRequested() else PREFIXE

        if not self._verbes:
            return True, ""
        commande = compat.commande_winetricks(self._lanceur, self._verbes)
        if commande is None:
            return False, WINETRICKS_ABSENT
        self.etape.emit("composants", " ".join(self._verbes))
        code = self._executer(commande, compat.environnement(self._lanceur, self._prefixe))
        if code is None:
            return False, ANNULEE
        installes = compat.verbes_installes(self._prefixe)
        if code != 0 and not {v.lower() for v in self._verbes} <= installes:
            return False, COMPOSANTS
        return True, ""

    def _attendre(self, condition, delai_s: float) -> bool:
        limite = time.monotonic() + delai_s
        while time.monotonic() < limite:
            if condition():
                return True
            if self.isInterruptionRequested():
                return False
            time.sleep(_PAS_S)
        return condition()

    def _executer(self, commande: list[str], env: dict[str, str]) -> int | None:
        """Exécute une commande, sortie au journal. None si interrompue.

        Nouvelle session : à l'annulation (fermeture du launcher), c'est tout le
        groupe qu'on arrête — umu, le conteneur et winetricks —, pas seulement
        le processus qu'on a lancé.
        """
        with open(self._journal, "ab") as sortie:
            entete = f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} : {' '.join(commande)}\n"
            sortie.write(entete.encode("utf-8", "replace"))
            sortie.flush()
            # Programme trouvé par chemin ABSOLU (`compat._trouver`), verbes
            # tirés d'une table du launcher ; liste d'arguments, aucun shell.
            proc = subprocess.Popen(  # nosec B603
                commande, env=env, cwd=str(self._prefixe), stdin=subprocess.DEVNULL,
                stdout=sortie, stderr=subprocess.STDOUT, start_new_session=True)
            while True:
                try:
                    code = proc.wait(timeout=_PAS_S)
                    log.info("%s → code %s", commande[0], code)
                    return code
                except subprocess.TimeoutExpired:
                    if self.isInterruptionRequested():
                        self._arreter(proc)
                        return None

    @staticmethod
    def _arreter(proc: subprocess.Popen) -> None:
        """SIGTERM au groupe, puis SIGKILL s'il traîne."""
        for sig in (signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)):
            try:
                os.killpg(proc.pid, sig)
            except (OSError, AttributeError):
                proc.kill()
            try:
                proc.wait(timeout=_ARRET_S)
                return
            except subprocess.TimeoutExpired:
                continue
