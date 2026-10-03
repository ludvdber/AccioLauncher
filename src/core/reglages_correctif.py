"""Réglages du correctif PC de HP4 à HP7 partie 2, lus et écrits dans son `d3d9.ini`.

Le correctif (dépôt Harry-Potter-PC-Fix) lit un `d3d9.ini` à côté de l'exécutable
du jeu. Ce module en règle QUELQUES clés depuis le lanceur ; tout le reste du
fichier appartient au joueur et n'est jamais réécrit.

Trois règles :

- **Seulement ce qui a été VU en jeu.** Le catalogue déclare, jeu par jeu, les
  réglages confirmés (`fix_settings`) ; un identifiant inconnu d'une version
  plus ancienne du lanceur est ignoré. Proposer un réglage qu'on n'a jamais
  regardé tourner, c'est déplacer le test chez le joueur.
- **Seulement le NOUVEAU correctif.** Les archives publiées portent encore
  l'ancien wrapper, dont l'ini n'a pas ces clés : on le reconnaît à l'absence
  de `[Accio.Window]`, et l'interface dit alors que les réglages arrivent avec
  la prochaine version, au lieu d'écrire des clés que personne ne lira.
- **Une édition en place.** Commentaires, ordre, fins de ligne (CRLF) et
  encodage restent ceux du fichier : seule la ligne de la clé change.
"""

from __future__ import annotations

import logging
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from src.core.i18n import decimal_separator, tr

from src.core.reglages_table import (  # noqa: F401  (réexportés)
    LIMITES_FPS,
    ECHANTILLONS_MSAA,
    FILTRAGES,
    VIVACITES,
    CONTRASTES,
    NETTETES,
    NETTETES_LOINTAINES,
    RESOLUTIONS,
    MODES_FENETRE,
    FORMATS,
    LANGUES_MENU,
    _POSITIONS,
    _SOURIS,
    _PANNEAU,
    _RESOLUTION,
    Reglage,
    REGLAGES,
    PREREGLAGES,
)

log = logging.getLogger(__name__)

NOM_INI = "d3d9.ini"
# Copie de l'ini tel qu'il était AVANT la première retouche du lanceur : ce que
# « Rétablir les réglages d'origine » remet en place.
SUFFIXE_ORIGINE = ".origine"
_MARQUE_V2 = "Accio.Window"   # section qu'a seul le nouveau correctif


def _lettre(scan: int, repli: str) -> str:
    """La lettre imprimée à cette position sur le clavier actif (Windows).

    Ailleurs, la position US : sous Linux le jeu tourne sous Wine, dont la
    disposition ne se lit pas d'ici, et un QWERTY est le cas le plus répandu.
    """
    if sys.platform != "win32":
        return repli
    try:
        import ctypes
        vk = ctypes.windll.user32.MapVirtualKeyW(scan, 1)   # MAPVK_VSC_TO_VK
    except (AttributeError, OSError):
        return repli
    # Pour une lettre, le code de touche virtuelle EST la majuscule ASCII.
    return chr(vk) if 0x41 <= vk <= 0x5A else repli


def touches_preregle() -> tuple[tuple[str, str], ...]:
    """(action, touche) du préréglage, pour le clavier de CE poste."""
    return tuple((action, _lettre(scan, us)) for action, scan, us in _POSITIONS) + _SOURIS


def allume(reglage: Reglage, valeur) -> bool:
    """Le réglage agit-il ? Un interrupteur coché, ou un choix autre que le premier (l'« éteint »)."""
    if reglage.choix:
        return valeur != reglage.choix[0]
    return bool(valeur)


def eteint(reglage: Reglage):
    """La valeur qui l'éteint."""
    return reglage.choix[0] if reglage.choix else False


def bloque_par(reglage: Reglage, valeurs: dict) -> Reglage | None:
    """Le réglage ÉTEINT dont dépend celui-ci (directement ou non), ou None s'il agit.

    `valeurs` : identifiant → valeur, pour les réglages présents dans la fenêtre.
    Un parent absent (non déclaré pour ce jeu) ne bloque rien.
    """
    parent = REGLAGES.get(reglage.depend_de)
    while parent is not None and parent.ident in valeurs:
        if not allume(parent, valeurs[parent.ident]):
            return parent
        parent = REGLAGES.get(parent.depend_de)
    return None


def libelle_choix(reglage: Reglage, valeur) -> str:
    """Ce que la liste déroulante affiche pour une valeur."""
    if reglage.noms_choix:
        if valeur == reglage.choix[0]:
            return tr(reglage.zero)
        return dict(reglage.noms_choix).get(valeur, str(valeur))
    if valeur == reglage.choix[0]:
        return tr(reglage.zero)
    if reglage.etiquettes:
        return tr(dict(reglage.etiquettes).get(valeur, _nombre(valeur)))
    return reglage.format_choix.format(_nombre(valeur).replace(".", decimal_separator()))


def _nombre(valeur) -> str:
    """1.5 → « 1.5 », 2.0 → « 2 » : ce que lit le correctif, sans décimale inutile."""
    return f"{valeur:g}" if isinstance(valeur, float) else str(valeur)


def textes(reglage: Reglage) -> tuple[str, str]:
    """(libellé, aide) traduits, avec les lettres du clavier de ce poste."""
    if reglage.ident != "touches_zqsd":
        return tr(reglage.libelle), tr(reglage.aide)
    t = dict(touches_preregle())
    deplacement = t["MoveUp"] + t["MoveLeft"] + t["MoveDown"] + t["MoveRight"]
    return (tr(reglage.libelle).format(deplacement),
            tr(reglage.aide).format(deplacement, t["Accio"], t["Extremos"], t["MoveDown"]))

def reglages_du_jeu(idents) -> tuple[Reglage, ...]:
    """Les réglages déclarés par le catalogue, connus de CE lanceur, dans l'ordre d'affichage."""
    voulus = set(idents or ())
    return tuple(r for r in REGLAGES.values() if r.ident in voulus)


def prereglages_du_jeu(reglages) -> tuple[tuple[str, str, str, dict], ...]:
    """Les préréglages réduits aux réglages que CE jeu déclare ; () s'il y en a trop peu.

    Moins de trois réglages en commun, un préréglage ne résumerait rien : le
    détail suffit.
    """
    presents = {r.ident for r in reglages}
    reduits = tuple((ident, nom, texte, {k: v for k, v in valeurs.items() if k in presents})
                    for ident, nom, texte, valeurs in PREREGLAGES)
    return reduits if len(reduits[0][3]) >= 3 else ()


def prereglage_courant(prereglages, valeurs: dict) -> str:
    """L'identifiant du préréglage que portent `valeurs` (identifiant → valeur), "" sinon."""
    for ident, _nom, _texte, voulues in prereglages:
        if all(k in valeurs and valeurs[k] == v for k, v in voulues.items()):
            return ident
    return ""


def chemin_ini(dossier_exe: Path) -> Path:
    return dossier_exe / NOM_INI


# ── Lecture et écriture de l'ini, en place ──

_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _lire(chemin: Path) -> tuple[list[str], str]:
    """Lignes SANS fin de ligne, et la fin de ligne du fichier."""
    brut = chemin.read_bytes().decode("utf-8", errors="surrogateescape")
    fin = "\r\n" if "\r\n" in brut else "\n"
    return brut.split(fin), fin


def _ecrire(chemin: Path, lignes: list[str], fin: str) -> None:
    texte = fin.join(lignes)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_bytes(texte.encode("utf-8", errors="surrogateescape"))
    tmp.replace(chemin)


def _bornes(lignes: list[str], section: str) -> tuple[int, int] | None:
    """(première ligne après l'en-tête, ligne de la section suivante), ou None."""
    debut = None
    for i, ligne in enumerate(lignes):
        m = _SECTION.match(ligne)
        if not m:
            continue
        if debut is not None:
            return debut, i
        if m.group(1).strip().lower() == section.lower():
            debut = i + 1
    return (debut, len(lignes)) if debut is not None else None


def _motif_cle(cle: str, commentee: bool) -> re.Pattern:
    prefixe = r"\s*;\s*" if commentee else r"\s*"
    return re.compile(prefixe + re.escape(cle) + r"\s*=(.*)$", re.IGNORECASE)


def _valeur(lignes: list[str], section: str, cle: str) -> str | None:
    bornes = _bornes(lignes, section)
    if bornes is None:
        return None
    motif = _motif_cle(cle, commentee=False)
    for ligne in lignes[bornes[0]:bornes[1]]:
        m = motif.match(ligne)
        if m:
            # Le correctif lit ses valeurs avec les commentaires de fin de ligne
            # (« 100 // max fps » dans les anciens ini) : ne garder que la valeur.
            return re.split(r"\s*(?://|;)", m.group(1), maxsplit=1)[0].strip()
    return None


def _poser(lignes: list[str], section: str, cle: str, valeur: str | None) -> bool:
    """Pose `cle=valeur` (ou la commente si valeur est None). False si la section manque."""
    bornes = _bornes(lignes, section)
    if bornes is None:
        return False
    debut, fin = bornes
    active, commentee = _motif_cle(cle, False), _motif_cle(cle, True)
    for i in range(debut, fin):
        if active.match(lignes[i]) or commentee.match(lignes[i]):
            lignes[i] = f"{cle}={valeur}" if valeur is not None else f";{cle}={_ancienne(lignes[i])}"
            return True
    if valeur is None:
        return True   # rien à commenter
    # Clé absente : juste après la dernière ligne non vide de la section.
    j = fin
    while j > debut and not lignes[j - 1].strip():
        j -= 1
    lignes.insert(j, f"{cle}={valeur}")
    return True


def _ancienne(ligne: str) -> str:
    return ligne.split("=", 1)[1].strip() if "=" in ligne else ""


# ── Ce que voit l'interface ──

@dataclass(frozen=True)
class Etat:
    """Ce que porte l'ini pour un réglage.

    `valeur` : bool pour un interrupteur, int pour un réglage à choix.
    `personnalise` : l'ini porte une valeur que l'interface ne sait pas
    représenter (touches choisies à la main) — on l'affiche, on ne l'écrase pas.
    """
    valeur: object
    personnalise: bool = False


def est_nouveau_correctif(ini: Path) -> bool:
    try:
        lignes, _ = _lire(ini)
    except OSError:
        return False
    return _bornes(lignes, _MARQUE_V2) is not None


def lire(ini: Path, reglage: Reglage) -> Etat:
    lignes, _ = _lire(ini)
    if reglage.ident == "touches_zqsd":
        preregle = touches_preregle()
        actives = {cle: _valeur(lignes, reglage.section, cle) for cle, _ in preregle}
        if all(actives[cle] is not None and actives[cle].lower() == v.lower() for cle, v in preregle):
            return Etat(True)
        return Etat(False, personnalise=any(v is not None for v in actives.values()))
    if reglage.ident == "panneau_perfs":
        # Un mélange (quelques lignes à la main) se montre éteint et se signale.
        allumees = [_valeur(lignes, reglage.section, cle) not in (None, "0", "") for cle in _PANNEAU]
        return Etat(all(allumees), personnalise=any(allumees) and not all(allumees))
    if reglage.ident == "resolution":
        largeur, hauteur = (_valeur(lignes, reglage.section, cle) for cle in _RESOLUTION)
        if largeur is None and hauteur is None:
            return Etat(reglage.choix[0])
        v = f"{(largeur or '').strip()}x{(hauteur or '').strip()}"
        return Etat(v, personnalise=v not in reglage.choix)
    brut = _valeur(lignes, reglage.section, reglage.cle)
    if reglage.noms_choix:
        # Le correctif compare sans tenir compte de la casse.
        v = brut.lower() if brut else reglage.choix[0]
        return Etat(v, personnalise=v not in reglage.choix)
    if reglage.choix:
        # Un facteur peut être décimal (SSAAFactor=1.5) ; un entier reste un int.
        try:
            n = float(brut) if brut is not None else reglage.choix[0]
        except ValueError:
            return Etat(0, personnalise=True)
        if isinstance(n, float) and n.is_integer():
            n = int(n)
        return Etat(n, personnalise=n not in reglage.choix)
    # Interrupteur : le correctif lit 0 = non, tout autre nombre = oui.
    if brut is None:
        return Etat(reglage.defaut)
    return Etat(brut.strip() not in ("0", ""))


def touche_capture(ini: Path) -> str:
    """La touche de capture que lira le correctif, telle qu'on la montre (« F12 »), ou "".

    Lue dans l'ini plutôt que déclarée : seul le NOUVEAU correctif en a une, et
    un joueur a pu la changer (`ScreenshotKey`, code de touche Windows, 0 = aucune).
    """
    if not est_nouveau_correctif(ini):
        return ""
    try:
        lignes, _ = _lire(ini)
    except OSError:
        return ""
    brut = _valeur(lignes, _MARQUE_V2, "ScreenshotKey")
    try:
        code = int(brut) if brut is not None else 0x7B   # défaut du correctif : F12
    except ValueError:
        return ""
    if 0x70 <= code <= 0x87:
        return f"F{code - 0x6F}"
    if code == 0x2C:
        return tr("Impr. écran")
    if 0x30 <= code <= 0x5A:
        return chr(code)
    return ""


def poser_valeur(ini: Path, section: str, cle: str, valeur: str) -> bool:
    """Pose une clé que le LANCEUR tient à jour (pas un réglage de l'interface).

    N'écrit que si la valeur change : le fichier n'est pas réécrit à chaque
    lancement pour rien. Rend True s'il a été écrit. Lève OSError si le fichier
    ne peut pas l'être, ValueError si la section manque ou si la valeur ferait
    une seconde ligne.
    """
    if any(c in valeur for c in "\r\n\x00"):
        raise ValueError(f"{cle} : valeur sur plusieurs lignes")
    lignes, fin = _lire(ini)
    if _valeur(lignes, section, cle) == valeur:
        return False
    if not _poser(lignes, section, cle, valeur):
        raise ValueError(f"section [{section}] absente")
    _ecrire(ini, lignes, fin)
    return True


def chemin_origine(ini: Path) -> Path:
    return ini.with_name(ini.name + SUFFIXE_ORIGINE)


def _garder_origine(ini: Path) -> None:
    """Copie l'ini AVANT la première retouche d'un réglage, une fois pour toutes.

    Un échec n'empêche pas le réglage : il ne coûte que la remise à l'origine.
    """
    copie = chemin_origine(ini)
    if copie.exists():
        return
    try:
        shutil.copy2(ini, copie)
    except OSError:
        log.warning("Correctif : copie d'origine de %s impossible", ini, exc_info=True)


def _cles(reglage: Reglage) -> tuple[str, ...]:
    if reglage.ident == "touches_zqsd":
        # Toutes les actions, pas seulement celles du préréglage : l'éditeur de
        # touches (touches_correctif, qui importe ce module) règle aussi Pause,
        # Valider et Retour.
        from src.core.touches_correctif import ACTIONS
        return tuple(a.cle for a in ACTIONS)
    if reglage.ident == "panneau_perfs":
        return _PANNEAU
    if reglage.ident == "resolution":
        return _RESOLUTION
    return (reglage.cle,)


# Le plafond que le correctif tient DANS le jeu (HP4-HP6 : 120). Au-dessous de
# la limite choisie, c'est lui qui l'emporte : « 144 » donnait 120 images, même
# sans synchro (Ludo, 2026-10-01). Il suit donc la limite vers le HAUT ; jamais
# vers le bas (un plafond livré n'est pas une préférence qu'on retire).
_PLAFOND = ("Accio.Game", "FrameRateCap")


def _relever_plafond(lignes: list[str], limite) -> None:
    actuel = _valeur(lignes, *_PLAFOND)
    if actuel is None or not limite:
        return
    try:
        plafond = int(float(actuel))
    except ValueError:
        return
    if 0 < plafond < int(limite):
        _poser(lignes, *_PLAFOND, str(int(limite)))


def a_une_origine(ini: Path) -> bool:
    return chemin_origine(ini).is_file()


def remettre_origine(ini: Path, reglages) -> None:
    """Remet les clés de CES réglages telles que les portait l'ini d'origine.

    Seulement les clés que le lanceur règle : le reste du fichier (touches
    posées à la main, dossier des captures) ne bouge pas. Une clé absente de
    l'origine est commentée, donc rendue au défaut du correctif. Lève OSError
    si un des deux fichiers ne peut pas être lu ou écrit.
    """
    origine, _ = _lire(chemin_origine(ini))
    lignes, fin = _lire(ini)
    for reglage in reglages:
        for cle in _cles(reglage):
            _poser(lignes, reglage.section, cle, _valeur(origine, reglage.section, cle))
        if reglage.cle == "FPSLimit" and _valeur(lignes, *_PLAFOND) is not None:
            _poser(lignes, *_PLAFOND, _valeur(origine, *_PLAFOND))
    _ecrire(ini, lignes, fin)
    log.info("Correctif : réglages d'origine remis dans %s", ini)


def ecrire(ini: Path, reglage: Reglage, valeur) -> None:
    """Écrit un réglage. Lève OSError si le fichier ne peut pas être écrit,
    ValueError si la valeur n'est pas de celles que l'interface propose."""
    lignes, fin = _lire(ini)
    _garder_origine(ini)
    if reglage.ident == "touches_zqsd":
        for cle, touche in touches_preregle():
            if not _poser(lignes, reglage.section, cle, touche if valeur else None):
                raise ValueError(f"section [{reglage.section}] absente")
    elif reglage.ident == "panneau_perfs":
        for cle in _PANNEAU:
            if not _poser(lignes, reglage.section, cle, "1" if valeur else "0"):
                raise ValueError(f"section [{reglage.section}] absente")
    elif reglage.ident == "resolution":
        if valeur not in reglage.choix:
            raise ValueError(f"{reglage.ident} : {valeur!r} non proposé")
        for cle, nombre in zip(_RESOLUTION, valeur.split("x")):
            if not _poser(lignes, reglage.section, cle, nombre):
                raise ValueError(f"section [{reglage.section}] absente")
    elif reglage.choix:
        if valeur not in reglage.choix:
            raise ValueError(f"{reglage.ident} : {valeur!r} non proposé")
        texte = str(valeur) if reglage.noms_choix else _nombre(valeur)
        if not _poser(lignes, reglage.section, reglage.cle, texte):
            raise ValueError(f"section [{reglage.section}] absente")
        if reglage.cle == "FPSLimit":
            _relever_plafond(lignes, valeur)
    else:
        if not _poser(lignes, reglage.section, reglage.cle, "1" if valeur else "0"):
            raise ValueError(f"section [{reglage.section}] absente")
    _ecrire(ini, lignes, fin)
    log.info("Correctif : %s = %r dans %s", reglage.ident, valeur, ini)
