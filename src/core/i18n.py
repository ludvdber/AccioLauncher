"""Internationalisation FR / EN / ES — sans dépendance Qt.

Le français est la langue SOURCE : les chaînes du code SONT les clés.
Les traductions vivent dans `src/data/i18n/<code>.json`, jamais dans ce module —
un traducteur bénévole n'a donc aucune ligne de Python à toucher :

    {"_meta": {"code": "es", "name": "Español", "translators": ["Nom"]},
     "strings": {"clé française": "traducción", …}}

Ajouter une langue = déposer un fichier. `available_languages()` le découvre
seul et le sélecteur des Paramètres l'affiche sans le moindre changement de code.

Repli en cascade : langue active → anglais → clé française. Une traduction
partielle reste donc utilisable telle quelle, ce qui permet d'accepter une
contribution à 60 % sans jamais afficher de trou.

Un fichier déposé dans `~/Games/AccioLauncher/i18n/<code>.json` est fusionné
par-dessus celui embarqué : un traducteur voit son travail dans le vrai
launcher, sans attendre ni merge ni release.

Les chaînes paramétrées utilisent des gabarits `{}` : `tr("Version {}").format(x)`.
Changer de langue nécessite un redémarrage (les chaînes sont posées à la
construction des widgets) — l'UI le précise.
"""

import json
import logging
import os
import sys
from typing import NamedTuple

from src.core.config import DEFAULT_LANGUAGE, I18N_DIR, USER_I18N_DIR

log = logging.getLogger(__name__)

# Langue dans laquelle le code est écrit : ses chaînes servent de clés.
SOURCE_LANGUAGE = "fr"
# `DEFAULT_LANGUAGE` (= "en") vient de config.py : c'est aussi la valeur par
# défaut de `Config.langue`, et config.py ne peut pas importer ce module.


class LanguageInfo(NamedTuple):
    """Une langue proposable à l'utilisateur."""
    code: str          # "fr", "en", "es"…
    name: str          # nom dans la langue elle-même ("Español")
    translators: tuple[str, ...]


_SOURCE_INFO = LanguageInfo(SOURCE_LANGUAGE, "Français", ("ASTeam",))

_lang = SOURCE_LANGUAGE
# Cache des dictionnaires chargés : code → {clé française: traduction}
_strings: dict[str, dict[str, str]] = {}
# Cache de la découverte des fichiers (None tant que rien n'a été scanné)
_catalogue: dict[str, LanguageInfo] | None = None


def _read_pack(path) -> tuple[dict[str, str], dict]:
    """Lit un fichier de langue. Retourne ({} , {}) si illisible ou aberrant.

    Un fichier de traduction peut venir d'une contribution extérieure ou du
    dossier utilisateur : il ne doit JAMAIS empêcher le launcher de démarrer.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Fichier de langue illisible (%s) : %s", path.name, exc)
        return {}, {}
    if not isinstance(raw, dict):
        log.warning("Fichier de langue aberrant (%s) : racine non-objet", path.name)
        return {}, {}
    meta = raw.get("_meta")
    strings = raw.get("strings")
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(strings, dict):
        log.warning("Fichier de langue sans bloc « strings » : %s", path.name)
        return {}, meta
    # On ne garde que les paires réellement exploitables — une valeur non-texte
    # ferait planter le premier setText() qui la reçoit.
    clean = {k: v for k, v in strings.items() if isinstance(k, str) and isinstance(v, str)}
    if len(clean) != len(strings):
        log.warning("%d entrée(s) ignorée(s) dans %s (valeur non-texte)",
                    len(strings) - len(clean), path.name)
    return clean, meta


def _discover() -> dict[str, LanguageInfo]:
    """Scanne les langues embarquées puis celles du dossier utilisateur."""
    global _catalogue
    if _catalogue is not None:
        return _catalogue

    found: dict[str, LanguageInfo] = {SOURCE_LANGUAGE: _SOURCE_INFO}
    for directory in (I18N_DIR, USER_I18N_DIR):
        try:
            paths = sorted(directory.glob("*.json"))
        except OSError:
            continue
        for path in paths:
            code = path.stem.lower()
            if code == SOURCE_LANGUAGE:
                continue  # le français est la source, il n'a pas de fichier
            strings, meta = _read_pack(path)
            if not strings:
                continue
            previous = _strings.get(code, {})
            # Le dossier utilisateur complète l'embarqué au lieu de l'écraser :
            # une surcharge partielle reste utilisable.
            _strings[code] = {**previous, **strings}
            names = meta.get("translators")
            translators = tuple(n for n in names if isinstance(n, str)) \
                if isinstance(names, list) else ()
            existing = found.get(code)
            found[code] = LanguageInfo(
                code=code,
                name=str(meta.get("name") or (existing.name if existing else code.upper())),
                translators=tuple(dict.fromkeys((existing.translators if existing else ())
                                                + translators)),
            )

    _catalogue = found
    return found


def available_languages() -> tuple[LanguageInfo, ...]:
    """Langues proposables : le français d'abord, puis les autres par code."""
    found = _discover()
    others = sorted((info for code, info in found.items() if code != SOURCE_LANGUAGE),
                    key=lambda i: i.code)
    return (found[SOURCE_LANGUAGE], *others)


def is_supported(lang: str) -> bool:
    return lang in _discover()


def detect_system_language() -> str:
    """Langue du système si elle est disponible, sinon `DEFAULT_LANGUAGE`.

    Volontairement sans Qt (ce module est importé par du code métier pur) et
    sans supposer Windows : le portage Linux passe par les variables d'env.
    """
    raw = ""
    if sys.platform == "win32":
        try:
            import ctypes
            # Identifiant primaire de langue : les 10 bits de poids faible.
            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            raw = {0x09: "en", 0x0A: "es", 0x0C: "fr"}.get(primary, "")
        except (AttributeError, OSError) as exc:
            log.debug("Langue système Windows indéterminable : %s", exc)
    if not raw:
        for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
            value = os.environ.get(var, "")
            if value:
                raw = value.split(".")[0].split("_")[0].split(":")[0].lower()
                break
    return raw if raw and is_supported(raw) else DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    """Fixe la langue active. Une langue inconnue retombe sur la source."""
    global _lang
    _lang = lang if is_supported(lang) else SOURCE_LANGUAGE


def get_language() -> str:
    return _lang


def tr(text: str) -> str:
    """Traduit une chaîne source française vers la langue active.

    Repli en cascade : langue active → anglais → français (la clé). Un trou de
    traduction dégrade donc vers une langue lisible, jamais vers du vide.
    """
    if _lang == SOURCE_LANGUAGE:
        return text
    _discover()
    hit = _strings.get(_lang, {}).get(text)
    if hit is not None:
        return hit
    if _lang != DEFAULT_LANGUAGE:
        hit = _strings.get(DEFAULT_LANGUAGE, {}).get(text)
        if hit is not None:
            return hit
    return text


def translator_credits() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """(nom de langue, traducteurs) pour l'écran « À propos ».

    Le français est exclu : c'est la langue source, elle n'est pas traduite.
    """
    return tuple((info.name, info.translators) for info in available_languages()
                 if info.code != SOURCE_LANGUAGE and info.translators)


def _reset_for_tests() -> None:
    """Vide les caches de découverte (tests uniquement)."""
    global _catalogue
    _catalogue = None
    _strings.clear()
