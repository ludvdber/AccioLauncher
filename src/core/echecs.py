"""Pourquoi un téléchargement a échoué — et ce qu'on peut y faire.

Jusqu'au 2026-09-18, la boîte d'échec disait « Vérifiez votre connexion
internet » QUELLE QUE SOIT la cause : disque plein, fichier mis en quarantaine
par un antivirus, empreinte fausse trois fois de suite, fichier retiré du
serveur. Accuser la connexion de quelqu'un dont le disque est plein, c'est
l'envoyer redémarrer sa box — et il reviendra au même point. C'est la même
faute que le faux « hors ligne » que le projet s'interdit : **quand le launcher
sait, il le dit**.

Le téléchargeur garde la DERNIÈRE exception de ses tentatives et la classe ici
(`cause_de`) ; la fenêtre affiche `explication`, suivie de ce qui est conservé
sur le disque. Module pur : aucun Qt, httpx importé paresseusement (jamais au
niveau du module, cf. `tests/test_imports_qt.py` et l'en-tête du téléchargeur).
"""

from __future__ import annotations

import errno
from dataclasses import dataclass

from src.core.formatting import format_bytes
from src.core.i18n import tr


class EmpreinteInvalide(OSError):
    """Le fichier reçu ne correspond pas à l'empreinte SHA-256 attendue."""


class TailleDepassee(OSError):
    """Le serveur envoie (ou annonce) plus que le plafond autorisé."""


# Codes Windows (`OSError.winerror`), relevés dans winerror.h.
_DISQUE_PLEIN = {39, 112}           # ERROR_HANDLE_DISK_FULL, ERROR_DISK_FULL
_ANTIVIRUS = {225, 226}             # ERROR_VIRUS_INFECTED, ERROR_VIRUS_DELETED
_ACCES = {5, 32, 33}                # ACCESS_DENIED, SHARING_VIOLATION, LOCK_VIOLATION


@dataclass(frozen=True)
class Echec:
    """Ce que la fenêtre a besoin de savoir d'un téléchargement raté."""

    cause: str = "inconnu"
    conserves: int = 0          # octets sur le disque, repris au prochain essai
    code_http: int = 0


def cause_de(exc: BaseException | None) -> tuple[str, int]:
    """(cause, code HTTP éventuel) d'une exception de téléchargement."""
    if exc is None:
        return "inconnu", 0
    if isinstance(exc, EmpreinteInvalide):
        return "empreinte", 0
    if isinstance(exc, TailleDepassee):
        return "inattendu", 0
    if isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        if winerror in _DISQUE_PLEIN or exc.errno == errno.ENOSPC:
            return "disque_plein", 0
        if winerror in _ANTIVIRUS:
            return "antivirus", 0
        if isinstance(exc, PermissionError) or winerror in _ACCES:
            return "acces_refuse", 0
        return "inconnu", 0
    try:
        import httpx
    except ImportError:
        return "inconnu", 0
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (404, 410):
            return "introuvable", code
        if code in (403, 429):
            return "limite", code
        return "serveur", code
    if isinstance(exc, httpx.HTTPError):
        return "connexion", 0
    return "inconnu", 0


def explication(echec: Echec) -> str:
    """Le texte de la boîte d'échec : la cause, ce qu'on peut faire, ce qui reste."""
    code = echec.code_http
    textes = {
        "connexion": tr("La connexion a été interrompue.\n"
                        "Vérifiez votre connexion internet et réessayez."),
        "disque_plein": tr("Le disque est plein.\nLibérez de la place, ou choisissez "
                           "un autre dossier d'installation dans les Paramètres."),
        "antivirus": tr("Votre antivirus a bloqué le fichier téléchargé.\n"
                        "Consultez sa quarantaine, puis réessayez."),
        "acces_refuse": tr("Windows a refusé l'accès au fichier téléchargé — le plus "
                           "souvent un antivirus en train de l'analyser.\nRéessayez "
                           "dans un instant ; si ça recommence, choisissez un autre "
                           "dossier dans les Paramètres."),
        "empreinte": tr("Le fichier reçu était abîmé, à chaque essai.\nCela vient "
                        "souvent d'un proxy, d'un antivirus qui inspecte les "
                        "téléchargements ou d'une connexion instable. Réessayez plus tard."),
        "inattendu": tr("Le serveur a envoyé un fichier plus gros que prévu, refusé "
                        "par sécurité.\nRéessayez plus tard ; si ça recommence, "
                        "signalez-le sur le Discord."),
        "introuvable": tr("Le fichier n'est plus sur le serveur (erreur {}).\nRelancez "
                          "le launcher pour récupérer le catalogue à jour.").format(code),
        "limite": tr("Le serveur limite les téléchargements pour le moment (erreur {}).\n"
                     "Réessayez dans quelques minutes.").format(code),
        "serveur": tr("Le serveur de téléchargement a répondu par une erreur ({}).\n"
                      "Réessayez plus tard.").format(code),
    }
    texte = textes.get(echec.cause, tr(
        "Le téléchargement a échoué.\nRéessayez ; si ça recommence, "
        "le Discord peut vous aider."))
    if echec.conserves > 0:
        texte += "\n\n" + tr(
            "{} sont conservés : relancez pour reprendre là où ça s'est arrêté."
        ).format(format_bytes(echec.conserves))
    return texte


# ─── Installation ────────────────────────────────────────────────────────────
#
# Même faute, même remède, à l'étape suivante : jusqu'au 2026-10-08 la boîte
# d'échec d'INSTALLATION disait « L'archive est peut-être corrompue.
# Réessayez le téléchargement » quoi qu'il arrive (ACT-003). Retélécharger
# 4 Go ne libère pas un disque plein et ne convainc pas un antivirus.

# Messages propres de 7-Zip (anglais quelle que soit la langue de Windows),
# relevés le 2026-10-08 sur une archive tronquée, abîmée et qui n'en est pas
# une. 7-Zip écrit « Cannot » ou « Can not » selon les versions.
_ARCHIVE_ABIMEE = ("cannot open the file as", "unexpected end", "is not archive",
                   "data error", "crc failed", "headers error", "data after the end")
_ECRITURE_REFUSEE = ("cannot open output file", "cannot create", "access is denied")
# Sous ce seuil d'espace libre, un échec de 7-Zip est un disque plein : le
# message système que 7-Zip recopie est traduit (« Espace insuffisant sur le
# disque »), on ne peut pas le reconnaître au texte.
DISQUE_QUASI_PLEIN = 64 * 1024 * 1024
_CHEMIN_TROP_LONG = 206             # ERROR_FILENAME_EXCED_RANGE


def cause_installation(exc: BaseException | None, octets_libres: int | None = None) -> str:
    """Pourquoi une installation a échoué. Pure.

    `octets_libres` : l'espace restant sur le volume de destination, mesuré
    APRÈS l'échec — seul moyen de reconnaître un disque plein derrière un
    message de 7-Zip.
    """
    import zipfile
    import zlib

    from src.core.extractors import ArchiveRefusee, ExtractionEchouee, SeptZipIntrouvable

    if exc is None:
        return "inconnu"
    if isinstance(exc, ArchiveRefusee):
        return "refusee"
    if isinstance(exc, SeptZipIntrouvable):
        return "outil"
    if isinstance(exc, (zipfile.BadZipFile, EOFError, zlib.error)):
        return "archive"
    if isinstance(exc, ExtractionEchouee):
        sortie = exc.sortie.lower().replace("can not", "cannot")
        if octets_libres is not None and octets_libres < DISQUE_QUASI_PLEIN:
            return "disque_plein"
        if any(m in sortie for m in _ARCHIVE_ABIMEE):
            return "archive"
        if any(m in sortie for m in _ECRITURE_REFUSEE):
            return "acces_refuse"
        return "inconnu"
    if isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        if winerror in _DISQUE_PLEIN or exc.errno == errno.ENOSPC:
            return "disque_plein"
        if winerror in _ANTIVIRUS:
            return "antivirus"
        if winerror == _CHEMIN_TROP_LONG or exc.errno == errno.ENAMETOOLONG:
            return "chemin_long"
        if isinstance(exc, PermissionError) or winerror in _ACCES:
            return "acces_refuse"
    return "inconnu"


def explication_installation(cause: str, archive_du_launcher: bool = True) -> str:
    """Le texte de la boîte d'échec d'installation.

    `archive_du_launcher` : l'archive vient du cache du launcher (et non d'un
    fichier choisi par la personne). Seule une archive abîmée du cache est
    supprimée, donc seule elle peut être retéléchargée par un nouvel essai.
    """
    if cause == "archive":
        if archive_du_launcher:
            return tr("L'archive téléchargée est abîmée. Elle a été supprimée : "
                      "relancez l'installation pour la télécharger à nouveau.")
        return tr("L'archive choisie est abîmée ou incomplète.\nVérifiez-la, "
                  "ou installez le jeu depuis le launcher.")
    textes = {
        "disque_plein": tr("Le disque est plein.\nLibérez de la place, ou choisissez "
                           "un autre dossier d'installation dans les Paramètres."),
        "antivirus": tr("Votre antivirus a bloqué un fichier du jeu pendant "
                        "l'installation.\nConsultez sa quarantaine, puis réessayez."),
        "acces_refuse": tr("Windows a refusé l'écriture dans le dossier d'installation "
                           "— un antivirus, ou un dossier protégé.\nRéessayez ; si ça "
                           "recommence, choisissez un autre dossier dans les Paramètres."),
        "chemin_long": tr("Le chemin du dossier d'installation est trop long pour "
                          "Windows.\nChoisissez un dossier plus court dans les Paramètres."),
        "refusee": tr("Cette archive a été refusée par sécurité : elle voulait écrire "
                      "hors du dossier d'installation.\nSignalez-le sur le Discord."),
        "outil": tr("7-Zip est introuvable : le launcher ne peut pas décompresser ce "
                    "jeu.\nRéinstallez Accio Launcher."),
    }
    return textes.get(cause, tr("L'installation a échoué.\nRéessayez ; si ça "
                                "recommence, le Discord peut vous aider."))
