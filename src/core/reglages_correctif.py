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

import logging
import re
import shutil
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    CURSEURS,
    VALEURS_DU_JEU,
)
from src.core.reglages_table import ValeurChoix
from src.core.ecriture_atomique import ecrire_octets_atomique

# La valeur d'un réglage : un interrupteur (bool) ou l'un de ses choix.
type Valeur = ValeurChoix | bool
# Un préréglage : identifiant, nom, texte, {réglage : valeur}.
Prereglage = tuple[str, str, str, dict[str, Any]]

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


def allume(reglage: Reglage, valeur: object) -> bool:
    """Le réglage agit-il ? Un interrupteur coché, ou un choix autre que le premier (l'« éteint »)."""
    if reglage.choix:
        return bool(valeur != reglage.choix[0])
    return bool(valeur)


def eteint(reglage: Reglage) -> Valeur:
    """La valeur qui l'éteint."""
    return reglage.choix[0] if reglage.choix else False


def bloque_par(reglage: Reglage, valeurs: Mapping[str, object]) -> Reglage | None:
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


def libelle_choix(reglage: Reglage, valeur: Any) -> str:
    """Ce que la liste déroulante affiche pour une valeur."""
    if reglage.noms_choix:
        if valeur == reglage.choix[0]:
            return tr(reglage.zero)
        # tr() comme les réglages graphiques : un nom propre (« English ») ou une
        # taille (« 1280×720 ») n'a pas d'entrée et revient tel quel.
        return tr(dict(reglage.noms_choix).get(valeur, str(valeur)))
    if valeur == reglage.choix[0]:
        nom = tr(reglage.zero)
    elif reglage.etiquettes:
        nom = tr(dict(reglage.etiquettes).get(valeur, _nombre(valeur)))
    else:
        return reglage.format_choix.format(_nombre(valeur).replace(".", decimal_separator()))
    return f"{nom} ({texte_valeur(valeur)})" if reglage.chiffre else nom


def _nombre(valeur: object) -> str:
    """1.5 → « 1.5 », 2.0 → « 2 » : ce que lit le correctif, sans décimale inutile."""
    return f"{valeur:g}" if isinstance(valeur, float) else str(valeur)


def texte_valeur(valeur: object) -> str:
    """Une valeur lue dans le fichier, écrite pour la personne : « 0,28 » en français.

    Sert à la valeur « réglée à la main » qu'aucun choix de la liste ne porte :
    affichée brute, elle gardait le point de l'ini (« 0.28 »), une faute dans
    une interface française.
    """
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return str(valeur)
    # Le vrai signe moins, pas le trait d'union de l'ini (« −0,5 »).
    return _nombre(valeur).replace(".", decimal_separator()).replace("-", "−")


def rang_a_la_main(reglage: Reglage, valeur: object) -> int:
    """Où ranger dans la liste une valeur réglée à la main : entre les deux crans qui
    l'encadrent quand les choix sont des nombres en ordre, sinon à la fin."""
    fin = len(reglage.choix)
    nombres = [c for c in reglage.choix if isinstance(c, (int, float)) and not isinstance(c, bool)]
    if fin < 2 or len(nombres) != fin or isinstance(valeur, bool) \
            or not isinstance(valeur, (int, float)):
        return fin
    paires = list(zip(nombres, nombres[1:], strict=False))
    if all(a < b for a, b in paires):
        return next((i for i, c in enumerate(nombres) if valeur < c), fin)
    if all(a > b for a, b in paires):
        return next((i for i, c in enumerate(nombres) if valeur > c), fin)
    return fin


def curseur(reglage: Reglage) -> tuple[float, float, float] | None:
    """(min, max, pas) si ce réglage se règle au curseur gradué, None sinon."""
    return CURSEURS.get(reglage.ident)


def _decimales(pas: float) -> int:
    """Le nombre de décimales d'un pas : 0,05 → 2, 5 → 0."""
    texte = f"{pas:g}"
    return len(texte.split(".")[1]) if "." in texte else 0


def arrondir(reglage: Reglage, valeur: float) -> ValeurChoix:
    """La valeur ramenée au pas du curseur et dans ses bornes : 0,30000000000000004 → 0,3.

    Un entier reste un entier (force du halo : 60, pas 60.0) : le correctif lit
    `NativeBloomStrength` en entier."""
    bornes = curseur(reglage)
    if bornes is None:
        return valeur
    bas, haut, pas = bornes
    x = min(haut, max(bas, bas + round((valeur - bas) / pas) * pas))
    x = round(x, _decimales(pas))
    return int(x) if float(x).is_integer() else x


def sur_le_curseur(reglage: Reglage, valeur: object) -> bool:
    """Une valeur que le curseur de ce réglage sait poser : dans ses bornes, sur son pas."""
    bornes = curseur(reglage)
    if bornes is None or isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return False
    bas, haut, pas = bornes
    if not bas - 1e-9 <= valeur <= haut + 1e-9:
        return False
    return abs((valeur - bas) / pas - round((valeur - bas) / pas)) < 1e-6


def meme_valeur(a: object, b: object) -> bool:
    """Deux valeurs d'un réglage égales, aux arrondis de l'ini près (0.3 et 0.30000000000000004)."""
    if (isinstance(a, (int, float)) and isinstance(b, (int, float))
            and not isinstance(a, bool) and not isinstance(b, bool)):
        return abs(float(a) - float(b)) < 1e-6
    return a == b


def valeur_accio(ini: Path, reglage: Reglage) -> Valeur | None:
    """La valeur que livre Accio : celle de l'ini tel qu'installé (sa copie d'origine,
    gardée avant la première retouche), sinon celle de l'ini, encore jamais touché.
    None si aucun des deux ne se lit."""
    for chemin in (chemin_origine(ini), ini):
        if chemin.is_file():
            try:
                valeur = lire(chemin, reglage).valeur
            except OSError:
                continue
            if isinstance(valeur, (str, int, float)):   # bool compris
                return valeur
    return None


def valeur_du_jeu(reglage: Reglage) -> Valeur | None:
    """Ce que fait le jeu livré, sans le correctif ; None si on ne le sait pas (`VALEURS_DU_JEU`)."""
    return VALEURS_DU_JEU.get(reglage.ident)


def textes(reglage: Reglage) -> tuple[str, str]:
    """(libellé, aide) traduits, avec les lettres du clavier de ce poste."""
    if reglage.ident != "touches_zqsd":
        return tr(reglage.libelle), tr(reglage.aide)
    t = dict(touches_preregle())
    deplacement = t["MoveUp"] + t["MoveLeft"] + t["MoveDown"] + t["MoveRight"]
    return (tr(reglage.libelle).format(deplacement),
            tr(reglage.aide).format(deplacement, t["Accio"], t["Extremos"], t["MoveDown"]))

def reglages_du_jeu(idents: Iterable[str] | None) -> tuple[Reglage, ...]:
    """Les réglages déclarés par le catalogue, connus de CE lanceur, dans l'ordre d'affichage."""
    voulus = set(idents or ())
    return tuple(r for r in REGLAGES.values() if r.ident in voulus)


def prereglages_du_jeu(reglages: Iterable[Reglage]) -> tuple[Prereglage, ...]:
    """Les préréglages réduits aux réglages que CE jeu déclare ; () s'il y en a trop peu.

    Moins de trois réglages en commun, un préréglage ne résumerait rien : le
    détail suffit.
    """
    presents = {r.ident for r in reglages}
    reduits = tuple((ident, nom, texte, {k: v for k, v in valeurs.items() if k in presents})
                    for ident, nom, texte, valeurs in PREREGLAGES)
    return reduits if len(reduits[0][3]) >= 3 else ()


def prereglage_courant(prereglages: Iterable[Prereglage], valeurs: Mapping[str, object]) -> str:
    """L'identifiant du préréglage que portent `valeurs` (identifiant → valeur), "" sinon."""
    for ident, _nom, _texte, voulues in prereglages:
        if all(k in valeurs and valeurs[k] == v for k, v in voulues.items()):
            return ident
    return ""


def chemin_ini(dossier_exe: Path) -> Path:
    return dossier_exe / NOM_INI


# Les DLL du correctif de HP1-HP2 (winmm) et HP3 (dinput8) lisent les mêmes
# sections ([Accio.Window] : captures, FPSLimit ; [Accio.Overlay] : panneau)
# dans LEUR ini.
NOMS_INI = (NOM_INI, "winmm.ini", "dinput8.ini")


def ini_du_correctif(dossier_exe: Path) -> Path:
    """L'ini du nouveau correctif de ce jeu, quelle que soit sa DLL.

    Le premier trouvé ; à défaut le `d3d9.ini` (absent ou ancien, les appelants
    le savent déjà écarter). Déclarer des `fix_settings` à HP1-HP3 n'a de sens
    qu'avec une archive qui livre la DLL du 2026-10-21 ou plus récente.
    """
    for nom in NOMS_INI:
        ini = dossier_exe / nom
        if ini.is_file() and est_nouveau_correctif(ini):
            return ini
    return chemin_ini(dossier_exe)


# ── Lecture et écriture de l'ini, en place ──

_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _lire(chemin: Path) -> tuple[list[str], str]:
    """Lignes SANS fin de ligne, et la fin de ligne du fichier."""
    brut = chemin.read_bytes().decode("utf-8", errors="surrogateescape")
    fin = "\r\n" if "\r\n" in brut else "\n"
    return brut.split(fin), fin


def _ecrire(chemin: Path, lignes: list[str], fin: str) -> None:
    texte = fin.join(lignes)
    # Le temporaire est effacé sur un échec (disque plein, fichier verrouillé) :
    # un `d3d9.ini.tmp` restait sinon dans le dossier du jeu (audit du 2026-10-29).
    ecrire_octets_atomique(chemin, texte.encode("utf-8", errors="surrogateescape"))


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


def _motif_cle(cle: str, commentee: bool) -> re.Pattern[str]:
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

    `valeur` : bool pour un interrupteur, la valeur du choix sinon (int, float
    ou str : « 1920x1080 », un nom de choix).
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


def portes_par(ini: Path | None, reglages: tuple[Reglage, ...]) -> tuple[Reglage, ...]:
    """Les réglages dont l'ini du nouveau correctif porte la section.

    Une section que la DLL installée ne connaît pas encore ([Accio.Hardcore]
    avant le correctif 2.2.0) ne s'affiche pas : son écriture échouerait. Sans
    ini lisible ou avec l'ancien correctif, tout reste, et la page dit pourquoi.
    """
    if ini is None or not est_nouveau_correctif(ini):
        return reglages
    try:
        lignes, _ = _lire(ini)
    except OSError:
        return reglages
    return tuple(r for r in reglages if _bornes(lignes, r.section) is not None)


def lire(ini: Path, reglage: Reglage) -> Etat:
    lignes, _ = _lire(ini)
    if reglage.ident == "touches_zqsd":
        preregle = touches_preregle()
        actives = {cle: _valeur(lignes, reglage.section, cle) for cle, _ in preregle}
        if all((actuel := actives[cle]) is not None and actuel.lower() == v.lower()
               for cle, v in preregle):
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
        choisi = brut.lower() if brut else reglage.choix[0]
        return Etat(choisi, personnalise=choisi not in reglage.choix)
    if reglage.choix:
        # Un facteur peut être décimal (SSAAFactor=1.5) ; un entier reste un int.
        try:
            n = float(brut) if brut is not None else reglage.choix[0]
        except ValueError:
            return Etat(0, personnalise=True)
        if isinstance(n, float) and n.is_integer():
            n = int(n)
        return Etat(n, personnalise=n not in reglage.choix and not sur_le_curseur(reglage, n))
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


def valeur_posee(ini: Path, section: str, cle: str) -> str | None:
    """La valeur d'une clé que le LANCEUR tient à jour, ou None si l'ini ne la porte pas."""
    try:
        lignes, _ = _lire(ini)
    except OSError:
        return None
    return _valeur(lignes, section, cle)


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


# Le plafond que le correctif tient DANS le jeu (HP4-HP6 : 120, livré égal à la
# limite). Au-dessous de la limite choisie, c'est lui qui l'emporte : « 144 »
# donnait 120 images, même sans synchro (Ludo, 2026-10-01). AU-DESSUS, il
# saccade : HP5 et HP6 avancent leur horloge de 1000/plafond ms par image
# dessinée, puis la rattrapent d'un pas fixe ; à 60 avec un plafond à 120,
# chaque image de 16,7 ms n'en avance que 8,3, d'où une image en dents de scie
# (#28, #29, 2026-11-06 : un joueur resté à 60/144 après avoir essayé 144).
# Le plafond SUIT donc la limite dans les deux sens ; « Aucune » lui rend sa
# valeur livrée. La cadence ne change pas : c'est le plus bas des deux qui tient.
# HP4 a la même horloge (lue dans son exe). MESURÉ en jeu le 2026-11-07 (HP5 et
# HP6, écran à 60 Hz) : 3 600 images par minute dont le rendu s'écarte de plus
# de 4 ms de la cadence affichée à 60/120, 0 à 60/60 et à 30/30 ; une marge
# (60/63, 30/32) en laisse 300. La synchro verticale fait la même chose sous le
# plafond livré (120 sur un écran à 60 ou 100 Hz) : le launcher ne la corrige
# pas, la fréquence lue par Windows n'étant pas celle qui cadence le jeu (59
# annoncé, 60,000 mesuré sur un PC à deux écrans). La vraie correction est
# `[Accio.Game] RealFrameTime=1` de la DLL (0 aussi dans tous ces cas, et 0
# avec plafond = limite : les deux cohabitent) ; ce réglage deviendra inutile
# quand plus aucun ini sans elle ne circulera.
_LIMITE = ("Accio.Window", "FPSLimit")
_PLAFOND = ("Accio.Game", "FrameRateCap")
_PLAFOND_LIVRE = 120


def _entier(texte: str | None) -> int | None:
    if texte is None:
        return None
    try:
        return int(float(texte))
    except (ValueError, OverflowError):
        # OverflowError : « inf » ou « 1e999 » écrit à la main ; le lancement ne doit pas s'arrêter là.
        return None


def _aligner_plafond(lignes: list[str], limite: Valeur | None, origine: Path) -> None:
    plafond = _entier(_valeur(lignes, *_PLAFOND))
    if not plafond or plafond < 0 or limite is None:
        # Absent, illisible ou 0 (HP3 : pas de plafond tenu) : rien à suivre.
        return
    cible = int(limite)
    if cible <= 0:
        livre = None
        if origine.is_file():
            livre = _entier(_valeur(_lire(origine)[0], *_PLAFOND))
        cible = livre if livre and livre > 0 else _PLAFOND_LIVRE
    if cible != plafond:
        _poser(lignes, *_PLAFOND, str(cible))


def aligner_plafond(ini: Path) -> bool:
    """Au lancement : remet le plafond du jeu à la limite d'images s'ils diffèrent.

    Rattrape les ini écrits avant que le plafond suive la limite vers le bas
    (60 avec 120 ou 144). Rien si l'une des deux clés manque ou vaut 0. N'écrit
    que si la valeur change ; rend True s'il a écrit. Lève OSError si le
    fichier ne peut pas être lu ou écrit.
    """
    lignes, _ = _lire(ini)
    limite = _entier(_valeur(lignes, *_LIMITE))
    plafond = _entier(_valeur(lignes, *_PLAFOND))
    if not limite or not plafond or limite < 0 or plafond < 0 or limite == plafond:
        return False
    return poser_valeur(ini, *_PLAFOND, str(limite))


def a_une_origine(ini: Path) -> bool:
    """Une copie d'origine qui diffère du fichier : il y a quelque chose à remettre.

    Depuis le 2026-11-13 l'installation pose la copie d'origine (`reglages_conserves`) :
    sa seule présence ne dit plus que le joueur a changé quelque chose.
    """
    origine = chemin_origine(ini)
    try:
        return origine.is_file() and (not ini.is_file() or origine.read_bytes() != ini.read_bytes())
    except OSError:
        return origine.is_file()


def remettre_origine(ini: Path, reglages: Iterable[Reglage]) -> None:
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


def ecrire(ini: Path, reglage: Reglage, valeur: Any) -> None:

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
        for cle, nombre in zip(_RESOLUTION, valeur.split("x"), strict=True):
            if not _poser(lignes, reglage.section, cle, nombre):
                raise ValueError(f"section [{reglage.section}] absente")
    elif reglage.choix:
        if valeur not in reglage.choix:
            if not sur_le_curseur(reglage, valeur):
                raise ValueError(f"{reglage.ident} : {valeur!r} non proposé")
            valeur = arrondir(reglage, valeur)
        texte = str(valeur) if reglage.noms_choix else _nombre(valeur)
        if not _poser(lignes, reglage.section, reglage.cle, texte):
            raise ValueError(f"section [{reglage.section}] absente")
        if reglage.cle == "FPSLimit":
            _aligner_plafond(lignes, valeur, chemin_origine(ini))
    else:
        if not _poser(lignes, reglage.section, reglage.cle, "1" if valeur else "0"):
            raise ValueError(f"section [{reglage.section}] absente")
    _ecrire(ini, lignes, fin)
    log.info("Correctif : %s = %r dans %s", reglage.ident, valeur, ini)
