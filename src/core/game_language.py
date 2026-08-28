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
- hors Windows, il n'y a rien à lire ni à écrire, et surtout rien à signaler
  comme un échec.

Ces fonctions prennent `game` et `config` EXPLICITEMENT au lieu de lire `self` :
elles s'exercent donc sans construire de `GameManager`, avec une config
fabriquée pour le cas qu'on veut. `GameManager` garde des méthodes qui y
délèguent — aucun appelant ne change.
"""

import logging

from src.core import game_registry as registre
from src.core.game_data import GameData
from src.core.i18n import get_language
from src.core.pre_launch import substitute_vars

log = logging.getLogger(__name__)


def langues_disponibles(game: GameData, config) -> tuple:
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
    lr = game.language_registry
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


def detecter(game: GameData) -> str | None:
    """Langue actuellement POSÉE dans le registre, None si indéterminable.

    La lecture est gratuite (aucun privilège) et c'est la seule source qui dise
    la vérité : le jeu peut avoir été installé par son installeur d'origine, ou
    l'utilisateur avoir changé la clé à la main.
    """
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


def resoudre(game: GameData, config) -> str | None:
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
    lr = game.language_registry
    # Sans registre atteignable (Linux), aucune langue n'est « celle du jeu » :
    # rien ne lit ni n'écrit ce réglage ici. Retourner None éteint le sélecteur
    # plutôt que d'afficher un choix sans effet — un réglage qui ne règle rien
    # est pire que pas de réglage.
    if not registre.disponible():
        return None
    if lr is None or not lr.languages:
        return None
    # Le choix et la détection portent sur TOUTES les langues déclarées : si le
    # registre annonce l'allemand, on l'affiche, même si les fichiers allemands
    # ne sont pas là — mieux vaut dire la vérité que la masquer. Seul le DÉFAUT
    # se restreint à ce que l'installation sait faire.
    choisi = config.game_language.get(game.id)
    if choisi and lr.get(choisi) is not None:
        return choisi
    detecte = detecter(game)
    if detecte is not None:
        return detecte
    possibles = langues_disponibles(game, config) or lr.languages
    interface = get_language()
    if any(lg.code == interface for lg in possibles):
        return interface
    return possibles[0].code


def memoriser(game: GameData | None, code: str, config) -> None:
    """Enregistre le choix de langue d'un jeu (persisté en config)."""
    if game is None or game.language_registry is None:
        return
    if game.language_registry.get(code) is None:
        log.warning("Langue %r non proposée par %s — ignorée",
                    code, game.id if game else "?")
        return
    config.game_language[game.id] = code
    config.save()
    log.info("Langue de %s : %s", game.id, code)


def valeurs_registre(game: GameData, config, code: str | None = None) -> dict:
    """Tout ce qui doit être posé dans la clé du jeu, langue comprise.

    Les valeurs communes (« Install Dir ») et celles de la langue vont dans la
    MÊME clé : les écrire ensemble, c'est un seul .reg et une seule invite UAC
    au lieu de deux à la suite. La langue passe en dernier — elle est plus
    spécifique, elle gagne en cas de collision de nom.
    """
    lr = game.language_registry
    if lr is None:
        return {}
    valeurs = {nom: substitute_vars(v, game, config) if isinstance(v, str) else v
               for nom, v in lr.common}
    code = code or resoudre(game, config)
    langue = lr.get(code) if code else None
    if langue is not None:
        valeurs.update(langue.as_dict)
    return valeurs


def appliquer(game: GameData, config, code: str | None = None,
              confirmer=None) -> bool:
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
    """
    lr = game.language_registry
    if lr is None:
        return True
    # Hors Windows il n'y a rien à écrire — et surtout pas d'avertissement à
    # journaliser À CHAQUE lancement pour une opération qu'on n'a pas tentée.
    # `launch_game` traite False comme un échec réel : ce n'en est pas un.
    if not registre.disponible():
        return True
    valeurs = valeurs_registre(game, config, code)
    if not valeurs:
        return True
    return registre.ecrire_valeurs(lr.root, lr.key, valeurs, lr.view,
                                   confirmer=confirmer)
