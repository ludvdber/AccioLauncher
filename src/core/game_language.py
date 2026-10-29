"""Langue d'un jeu : ce que le registre porte, ce qu'on peut lui proposer.

Extrait de `game_manager.py` le 2026-08-28. Le manager pesait 763 lignes et
mélangeait quatre métiers sans rapport (états sur disque, temps de jeu,
empreintes d'assets, langue) ; celui-ci est le plus autonome des quatre — il ne
touche NI les états, NI les stats, NI le cache, et il est le seul dont les
règles soient réellement subtiles :

- une langue ne se propose que si son fichier témoin est SUR LE DISQUE (le
  registre SÉLECTIONNE, il n'installe rien) ;
- les valeurs communes et celles de la langue partent dans la MÊME écriture,
  sinon deux invites UAC de suite — et la seconde se refuse ;
- sans registre atteignable (Linux sans Wine, ou préfixe pas encore
  préparé), il n'y a rien à lire ni à écrire, et surtout rien à signaler
  comme un échec.

Ces fonctions prennent `game` et `config` EXPLICITEMENT au lieu de lire `self` :
elles s'exercent donc sans construire de `GameManager`, avec une config
fabriquée pour le cas qu'on veut. `GameManager` garde des méthodes qui y
délèguent — aucun appelant ne change.
"""

import filecmp
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from src.core import game_registry as registre
from src.core.catalogue_blocs import GameLanguage, LangueFichiers
from src.core.config import Config
from src.core.game_data import GameData
from src.core.game_registry import Confirmer
from src.core.i18n import get_language
from src.core.pre_launch import ecrire_cle_ini, lire_cle_ini, substituer_pour_le_jeu

log = logging.getLogger(__name__)

# Deux façons de porter une langue, une seule surface pour l'UI :
# - `language_registry` (HP7) : des valeurs de registre, parfois sous HKLM ;
# - `language_files` (HP1) : des clés INI et des fichiers à recopier — ni
#   registre, ni élévation, et identique sous Wine.
# Les fonctions ci-dessous lisent `game.langues` quand la règle vaut pour les
# deux, et bifurquent seulement pour lire et écrire.


def langues_disponibles(game: GameData, config: Config) -> tuple[GameLanguage | LangueFichiers, ...]:
    """Langues que CETTE installation sait réellement faire.

    Le registre ne fait que SÉLECTIONNER une langue ; les fichiers, eux,
    viennent du disque d'origine. Un jeu installé en français n'a que les
    fichiers français, et basculer la clé sur l'anglais ne donnerait pas un jeu
    anglais (confirmé par deux guides communautaires : « you also have to copy
    the language file from the DVD to your installation path »). Proposer une
    langue que l'installation ne sait pas faire serait donc promettre quelque
    chose de faux.

    Mesuré : HP7 partie 1 n'embarque que `DH1_French.pck`, la partie 2 les sept.

    Une langue sans `requires_file` est toujours proposée : le contrôle est une
    option du catalogue, pas une obligation.
    """
    lr = game.langues
    if lr is None:
        return ()
    racine = config.install_path
    gardees = []
    for langue in lr.languages:
        if not langue.requires_file:
            gardees.append(langue)
            continue
        chemin = racine / langue.requires_file.replace("\\", "/")
        try:
            if chemin.exists():
                gardees.append(langue)
        except OSError:
            pass
    return tuple(gardees)


def detecter(game: GameData, config: Config | None = None) -> str | None:
    """Langue actuellement POSÉE (registre ou fichiers), None si indéterminable.

    La lecture est gratuite (aucun privilège) et c'est la seule source qui dise
    la vérité : le jeu peut avoir été installé par son installeur d'origine, ou
    l'utilisateur avoir changé la clé à la main.

    Pour une langue portée par des fichiers, `config` est nécessaire (chemins
    du jeu) ; sans lui, rien n'est lu.
    """
    if game.langue_par_fichiers:
        return _detecter_fichiers(game, config) if config is not None else None
    lr = game.language_registry
    if lr is None:
        return None
    noms = {nom for langue in lr.languages for nom, _ in langue.values}
    actuel = registre.lire_valeurs(lr.root, lr.key, sorted(noms), lr.view)
    if not actuel:
        return None
    for langue in lr.languages:
        if all(actuel.get(nom) == val for nom, val in langue.values):
            return langue.code
    return None


def resoudre(game: GameData, config: Config) -> str | None:
    """Code de la langue de CE jeu, None s'il n'en propose pas.

    Trois sources, dans l'ordre :
    1. le choix EXPLICITE de l'utilisateur, s'il est encore proposé ;
    2. ce que le registre porte RÉELLEMENT — sans quoi la fiche annoncerait une
       langue que le jeu n'a pas, et le lancement voudrait « corriger » le
       registre (donc demander une élévation) alors que l'utilisateur n'a rien
       demandé ;
    3. la langue de l'interface si le jeu la propose, sinon la première du
       catalogue. Surtout PAS la langue système : l'utilisateur a déjà dit sa
       langue à l'onboarding, et de toute façon aucun défaut figé ne peut
       convenir tant qu'il n'est pas modifiable.
    """
    lr = game.langues
    # Sans registre atteignable (Linux sans préfixe prêt), aucune langue n'est « celle du jeu » :
    # rien ne lit ni n'écrit ce réglage ici. Retourner None éteint le sélecteur
    # plutôt que d'afficher un choix sans effet — un réglage qui ne règle rien
    # est pire que pas de réglage. Une langue portée par des FICHIERS n'en
    # dépend pas.
    if game.language_registry is not None and not registre.disponible():
        return None
    if lr is None or not lr.languages:
        return None
    # Le choix et la détection portent sur TOUTES les langues déclarées : si le
    # registre annonce l'allemand, on l'affiche, même si les fichiers allemands
    # ne sont pas là — mieux vaut dire la vérité que la masquer. Seul le DÉFAUT
    # se restreint à ce que l'installation sait faire.
    choisi = config.game_language.get(game.id)
    if isinstance(choisi, str) and choisi and lr.get(choisi) is not None:
        return choisi
    detecte = detecter(game, config)
    if detecte is not None:
        return detecte
    possibles = langues_disponibles(game, config) or lr.languages
    interface = get_language()
    if any(lg.code == interface for lg in possibles):
        return interface
    return possibles[0].code


def memoriser(game: GameData | None, code: str, config: Config) -> None:
    """Enregistre le choix de langue d'un jeu (persisté en config)."""
    if game is None or game.langues is None:
        return
    if game.langues.get(code) is None:
        log.warning("Langue %r non proposée par %s — ignorée",
                    code, game.id if game else "?")
        return
    config.game_language[game.id] = code
    config.save()
    log.info("Langue de %s : %s", game.id, code)


def valeurs_registre(game: GameData, config: Config, code: str | None = None) -> dict[str, Any]:
    """Tout ce qui doit être posé dans la clé du jeu, langue comprise.

    Les valeurs communes (« Install Dir ») et celles de la langue vont dans la
    MÊME clé : les écrire ensemble, c'est un seul .reg et une seule invite UAC
    au lieu de deux à la suite. La langue passe en dernier — elle est plus
    spécifique, elle gagne en cas de collision de nom.
    """
    lr = game.language_registry
    if lr is None:
        return {}
    # Chemin tel que le JEU le lit : identique sous Windows, `Z:\…` sous Wine
    # (un `Install Dir` en chemin Unix ne mènerait le jeu nulle part).
    valeurs = {nom: substituer_pour_le_jeu(v, game, config) if isinstance(v, str) else v
               for nom, v in lr.common}
    code = code or resoudre(game, config)
    langue = lr.get(code) if code else None
    if langue is not None:
        valeurs.update(langue.as_dict)
    return valeurs


def appliquer(game: GameData, config: Config, code: str | None = None,
              confirmer: Confirmer | None = None) -> bool:
    """Écrit une langue dans le registre. True s'il n'y a rien à faire.

    `code` permet d'appliquer AVANT de persister : si l'écriture échoue (UAC
    refusé), on ne veut pas garder en config un choix que le registre n'a pas
    pris — sinon la fiche annoncerait une langue que le jeu n'a pas, et chaque
    lancement redemanderait l'élévation. Sans `code`, on applique ce que
    `resoudre` donne.

    Ne demande une élévation que si les valeurs DIFFÈRENT réellement : le cas
    courant est qu'elles sont déjà bonnes, et une invite UAC à chaque lancement
    serait pire que le problème qu'on règle.

    `confirmer(ruche, cle, valeurs)` est transmis tel quel : c'est l'UI qui
    prévient, et seulement quand il y a vraiment quelque chose à écrire.
    Une langue portée par des fichiers n'appelle jamais `confirmer` : rien ne
    sort du dossier du jeu et de sa configuration dans Documents.
    """
    if game.langue_par_fichiers:
        return _appliquer_fichiers(game, config, code)
    lr = game.language_registry
    if lr is None:
        return True
    # Sans registre atteignable il n'y a rien à écrire — et surtout pas d'avertissement à
    # journaliser À CHAQUE lancement pour une opération qu'on n'a pas tentée.
    # `launch_game` traite False comme un échec réel : ce n'en est pas un.
    if not registre.disponible():
        return True
    valeurs = valeurs_registre(game, config, code)
    if not valeurs:
        return True
    return registre.ecrire_valeurs(lr.root, lr.key, valeurs, lr.view,
                                   confirmer=confirmer)


_COPIES_GARDEES = 5      # par fichier remplacé, les plus récentes


def dossier_remplacees(game: GameData, langue: str) -> Path:
    """Où va un fichier qu'une partie plus récente vient de remplacer."""
    from src.core import config
    return config.LAUNCHER_DATA_PATH / "sauvegardes_remplacees" / game.id / langue


def porter_sauvegardes(game: GameData, config: Config) -> list[str]:
    """Recopie la partie et les réglages vers le dossier de la langue POSÉE.

    HP7 range `auto.sav` et `config.txt` dans un dossier nommé d'après son
    titre traduit : passé du français à l'anglais, il démarrait sans la partie
    et en 720p, l'image dans un coin (VU par Ludo le 2026-10-29). On copie
    chaque fichier du dossier où l'on a joué en DERNIER (`sauvegardes.dossier`)
    vers celui de la langue posée.

    **La plus récente gagne** (choix du 2026-10-29) : sans quoi revenir au
    français après une soirée en anglais rendait la vieille partie française.
    Un fichier n'est remplacé que s'il est plus ANCIEN et différent, et il part
    d'abord dans `dossier_remplacees` (les `_COPIES_GARDEES` dernières).

    Rend les noms copiés (vide le plus souvent). Une erreur de fichier n'empêche
    jamais le lancement.
    """
    from src.core import sauvegardes

    spec = game.sauvegardes
    lr = game.language_registry
    if spec is None or lr is None or not registre.disponible():
        return []
    code = detecter(game, config)
    langue = lr.get(code) if code is not None else None
    if langue is None or not langue.saves_folder:
        return []
    base = sauvegardes.racines().get(spec.racine)
    source = sauvegardes.dossier(spec)
    if base is None or source is None:
        return []
    cible = base / langue.saves_folder
    copies: list[str] = []
    try:
        if cible.resolve() == source.resolve():
            return []
        for fichier in sorted(source.iterdir()):
            if not fichier.is_file() or fichier.is_symlink():
                continue
            existant = cible / fichier.name
            if existant.exists():
                if (existant.is_symlink() or existant.stat().st_mtime >= fichier.stat().st_mtime
                        or filecmp.cmp(existant, fichier, shallow=False)):
                    continue
                _mettre_de_cote(existant, dossier_remplacees(game, code or ""))
            cible.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fichier, existant)
            copies.append(fichier.name)
    except OSError as e:
        log.warning("Sauvegardes de %s non recopiées vers %s : %s", game.id, cible, e)
    if copies:
        log.info("Langue de %s : %s recopiés de « %s » vers « %s »",
                 game.id, ", ".join(copies), source.name, cible.name)
    return copies


def _mettre_de_cote(fichier: Path, dossier: Path) -> None:
    """Copie datée de `fichier` avant qu'on le remplace ; lève OSError si elle
    échoue, et rien n'est alors remplacé."""
    dossier.mkdir(parents=True, exist_ok=True)
    date = time.strftime("%Y%m%d-%H%M%S", time.localtime(fichier.stat().st_mtime))
    shutil.copy2(fichier, dossier / f"{fichier.stem}-{date}{fichier.suffix}")
    anciennes = sorted(dossier.glob(f"{fichier.stem}-*{fichier.suffix}"), reverse=True)
    for vieille in anciennes[_COPIES_GARDEES:]:
        vieille.unlink(missing_ok=True)


# ─── Langue portée par des fichiers (HP1) ───

def _detecter_fichiers(game: GameData, config: Config) -> str | None:
    """La langue dont TOUTES les clés INI portent déjà la valeur, sinon None.

    Toutes, et pas la première : sur HP1, `HP.ini` et `Default.ini` doivent
    dire la même chose (avec `Running.ini` présent, c'est Default.ini qui
    décide), et un fichier sur deux ne fait pas une langue. La casse n'est pas
    comparée : le moteur écrit « fre », un joueur peut avoir écrit « FRE ».
    """
    if game.language_files is None:
        return None
    for langue in game.language_files.languages:
        valeurs = [lire_cle_ini(p, game, config) for p in langue.ini]
        if all(v is not None and v.casefold() == p.value.casefold()
               for v, p in zip(valeurs, langue.ini, strict=True)):
            return langue.code
    return None


def _appliquer_fichiers(game: GameData, config: Config, code: str | None) -> bool:

    """Pose une langue dans les fichiers du jeu. True si elle y est.

    Les COPIES d'abord (l'écran de démarrage anglais de HP1) : si l'une manque,
    on n'écrit pas la langue — HP1 en `int` sans `splashint.bmp` s'arrête au
    démarrage sur « Assertion failed: Bitmap.LoadFile » (vu, essai E4). Mieux
    vaut un jeu qui démarre dans l'ancienne langue. Une copie existante n'est
    jamais écrasée, et seule une clé qui DIFFÈRE est réécrite.
    """
    code = code or resoudre(game, config)
    langue = game.language_files.get(code) if code and game.language_files else None
    if langue is None:
        return True
    racine = config.install_path.resolve()
    for source, destination in langue.copies:
        src = (config.install_path / source.replace("\\", "/")).resolve()
        dst = (config.install_path / destination.replace("\\", "/")).resolve()
        if not (src.is_relative_to(racine) and dst.is_relative_to(racine)):
            log.warning("Copie de langue hors du dossier des jeux, refusée : %s → %s", src, dst)
            return False
        if dst.exists():
            continue
        try:
            shutil.copyfile(src, dst)
            log.info("Langue %s de %s : %s copié en %s", code, game.id, src.name, dst.name)
        except OSError as exc:
            log.warning("Langue %s de %s non posée, copie impossible (%s) : %s",
                        code, game.id, exc, dst)
            return False
    ok = True
    for patch in langue.ini:
        actuel = lire_cle_ini(patch, game, config)
        if actuel is not None and actuel.casefold() == patch.value.casefold():
            continue
        ok = ecrire_cle_ini(patch, game, config) and ok
    return ok
