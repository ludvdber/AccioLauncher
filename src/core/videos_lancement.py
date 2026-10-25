"""Passer les vidéos de lancement : les logos joués avant le menu (HP3).

Voulu par Ludo (2026-10-20), VU le 2026-10-21 dans l'atelier : les trois `.bik`
de HP3 (`eag_1920`, `wb_1920`, `KWLogo`) renommés en `.bik.off`, le jeu les
saute et le menu s'affiche à 6 s. Le catalogue les nomme (`launch_videos`).

Renommer et non effacer : remettre l'interrupteur rend les fichiers à
l'octet, et « Vérifier / réparer », qui reprend l'archive, les fait revenir de
toute façon. Seuls les fichiers déclarés, et leur `.off`, sont touchés.
Aucune fonction ne lève.
"""

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

SUFFIXE = ".off"


def _paire(dossier_jeux: Path, rel: str) -> tuple[Path, Path]:
    video = dossier_jeux / rel
    return video, video.with_name(video.name + SUFFIXE)


def passees(dossier_jeux: Path, videos: tuple[str, ...]) -> bool | None:
    """Vrai si plus aucune n'est jouée ; None si aucune n'est là, sous aucun nom.

    Une seule vidéo revenue (une réparation) suffit à dire « jouées » :
    l'interrupteur montre ce que le jeu fera au prochain lancement.
    """
    presentes = cachees = 0
    for rel in videos:
        video, cachee = _paire(dossier_jeux, rel)
        presentes += video.is_file()
        cachees += cachee.is_file()
    if presentes:
        return False
    return True if cachees else None


def passer(dossier_jeux: Path, videos: tuple[str, ...], oui: bool) -> bool:
    """Cache (oui) ou rend (non) chaque vidéo ; True si tout a été fait."""
    reussi = True
    for rel in videos:
        video, cachee = _paire(dossier_jeux, rel)
        try:
            if oui and video.is_file():
                os.replace(video, cachee)    # une vieille copie cachée est la même vidéo
            elif not oui and cachee.is_file():
                if video.is_file():
                    cachee.unlink()          # la réparation l'a déjà remise
                else:
                    os.replace(cachee, video)
        except OSError as exc:
            log.warning("Vidéo de lancement %s : %s", rel, exc)
            reussi = False
    if reussi:
        log.info("Vidéos de lancement %s (%d)", "passées" if oui else "remises", len(videos))
    return reussi
