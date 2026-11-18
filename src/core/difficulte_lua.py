"""La difficulté de HP6 par ses scripts Lua (Ludo, C1 et C1 bis du 2026-11-17).

HP6 livre un hôte Lua (`accio_hp6_hote.dll`, dépôt accio-moteur) et les modèles
de ses préréglages (`lua_modeles/*.lua`). Quand ils sont là, un réglage de
difficulté ne s'écrit plus dans `[Accio.Hardcore]` : le launcher pose le script
réglé dans `lua_launcher`, à côté de l'exécutable. L'hôte lit ce dossier AVANT
celui du joueur (`LuaFolder`), où le launcher n'écrit jamais ; un script du même
nom chez le joueur remplace le nôtre.

Ce module ne connaît ni l'ini ni l'interface : `reglages_correctif` décide de la
voie (`pret`) puis lit et écrit par ici, pour que presets et « Sur mesure »
passent par le même chemin. JAMAIS la clé du correctif et son script ensemble :
les deux se multiplient (atelier, `DIFFICULTE_1.4.md` § 8 bis : des duels mesurés
à ×9 pour ×3 voulu).

Ce que porte chaque réglage (C3 bis) :

- la valeur d'origine = script ABSENT, pas « facteur 1 » : poser 1 retirerait
  l'aide que le jeu s'accorde après une défaite ;
- `degats_recus` sous 1 MULTIPLIE le nombre du jeu (un 0,5 fixe serait plus dur
  que le jeu pour qui perd souvent) ; au-dessus de 1 il le remplace ;
- `degats_infliges` f devient la vie des adversaires × 1/f : le même effet ;
- `regeneration` garde cette part de la remontée du jeu, sans rien y ajouter.
"""

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from src.core.ecriture_atomique import ecrire_atomique

log = logging.getLogger(__name__)

HOTE = "accio_hp6_hote.dll"
DOSSIER_MODELES = "lua_modeles"
# Le nom que l'hôte cherche à côté de l'exécutable (`hote::DOSSIER_FOURNI`).
DOSSIER_FOURNI = "lua_launcher"
_FIN_REGLAGES = "-- FIN DES RÉGLAGES"


def _tel(valeur: float) -> float:
    return valeur


def _inverse(valeur: float) -> float:
    return round(1 / valeur, 4)


@dataclass(frozen=True)
class Traduction:
    script: str             # nom du modèle, sans extension
    variable: str           # le réglage d'en-tête qui porte la valeur
    vers_lua: Callable[[float], float] = _tel
    depuis_lua: Callable[[float], float] = _tel
    # Réglages d'en-tête posés tels quels, quelle que soit la valeur.
    fixes: tuple[tuple[str, str], ...] = ()
    # Sous 1, le facteur multiplie le nombre du jeu au lieu de le remplacer.
    multiplie_sous_un: bool = False


TRADUCTIONS: Mapping[str, Traduction] = {
    "degats_recus": Traduction("degats_recus", "facteur", multiplie_sous_un=True),
    "degats_infliges": Traduction("ennemis_plus_resistants", "vie", _inverse, _inverse),
    "reaction_ennemis": Traduction("ennemis_plus_vifs", "reaction"),
    "vie_joueur": Traduction("harry_plus_resistant", "vie"),
    "regeneration": Traduction("regeneration", "part_du_jeu", fixes=(("points", "0"),)),
}


def _modele(jeu: Path, ident: str) -> Path:
    return jeu / DOSSIER_MODELES / f"{TRADUCTIONS[ident].script}.lua"


def _pose(jeu: Path, ident: str) -> Path:
    return jeu / DOSSIER_FOURNI / f"{TRADUCTIONS[ident].script}.lua"


def pret(jeu: Path, ident: str, dossier_lua: str | None) -> bool:
    """Ce réglage passe-t-il par Lua dans ce jeu ? Il faut l'hôte, le modèle du
    script, et un dossier de scripts du joueur qui existe : sans `LuaFolder` le
    correctif ne charge pas l'hôte, et un script posé ne ferait rien."""
    if ident not in TRADUCTIONS or not dossier_lua or dossier_lua.strip() in ("", "0"):
        return False
    scripts = jeu / dossier_lua.strip()
    return (scripts.is_dir() and _modele(jeu, ident).is_file()
            and ((jeu / HOTE).is_file() or (scripts / HOTE).is_file()))


def _motif(variable: str) -> re.Pattern[str]:
    return re.compile(rf"^({re.escape(variable)} = )(\S+)", re.MULTILINE)


def _en_tete(source: str) -> str:
    """Le bloc des réglages : une affectation plus bas dans le script n'en est pas un."""
    return source.partition(_FIN_REGLAGES)[0]


def _lu(source: str, variable: str) -> str | None:
    trouve = _motif(variable).search(_en_tete(source))
    return trouve.group(2) if trouve else None


def _regle(source: str, variable: str, valeur: str) -> str:
    """Le script avec ce réglage d'en-tête changé. ValueError si le modèle ne le
    porte pas (un hôte plus ancien que ce launcher)."""
    en_tete = _en_tete(source)
    regle, combien = _motif(variable).subn(lambda m: m.group(1) + valeur, en_tete, count=1)
    if not combien:
        raise ValueError(f"réglage « {variable} » absent du modèle")
    return regle + source[len(en_tete):]


def _nombre(valeur: float) -> str:
    return f"{valeur:.4f}".rstrip("0").rstrip(".")


def lire(jeu: Path, ident: str, origine: float) -> float:
    """La valeur que porte le script posé ; `origine` s'il n'y en a pas, s'il est
    coupé ou illisible (il ne fait alors rien : c'est le jeu d'origine)."""
    traduction = TRADUCTIONS[ident]
    try:
        source = _pose(jeu, ident).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return origine
    brut = _lu(source, traduction.variable)
    if brut is None or _lu(source, "actif") == "false":
        return origine
    try:
        return round(traduction.depuis_lua(float(brut)), 2)
    except (ValueError, ZeroDivisionError):
        return origine


def ecrire(jeu: Path, ident: str, valeur: float, origine: float) -> None:
    """Pose le script réglé, ou le retire pour la valeur d'origine. Lève OSError
    si le dossier ne peut pas être écrit, ValueError si le modèle ne porte pas
    le réglage."""
    traduction = TRADUCTIONS[ident]
    pose = _pose(jeu, ident)
    if valeur == origine:
        pose.unlink(missing_ok=True)
        log.info("Difficulté Lua : %s retiré (jeu d'origine)", pose.name)
        return
    source = _modele(jeu, ident).read_text(encoding="utf-8")
    source = _regle(source, traduction.variable, _nombre(traduction.vers_lua(valeur)))
    for variable, fixe in traduction.fixes:
        source = _regle(source, variable, fixe)
    if traduction.multiplie_sous_un:
        source = _regle(source, "multiplier", "true" if valeur < 1 else "false")
    pose.parent.mkdir(exist_ok=True)
    ecrire_atomique(pose, source)
    log.info("Difficulté Lua : %s = %r dans %s", ident, valeur, pose)
