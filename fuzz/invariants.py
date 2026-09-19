"""Ce que les barrières du launcher promettent, écrit comme des assertions.

Le catalogue est DISTANT : de ce fichier sortent des chemins sur le disque de
l'utilisateur, des URL ouvertes dans son navigateur et des valeurs importées
dans le registre par un regedit ADMINISTRATEUR. Chaque fonction ci-dessous
prend une entrée quelconque et lève `AssertionError` si une barrière a laissé
passer ce qu'elle dit refuser.

Aucune dépendance à Atheris : les cibles `fuzz_*.py` les appellent avec des
millions d'entrées mutées (Linux, CI `fuzz.yml`), et `tests/test_fuzz.py` avec
des cas connus, pour que les invariants restent justes sous Windows aussi.
"""

import re
import unicodedata
from pathlib import Path

from src.core import game_registry as registre
from src.core.extractors import check_path_traversal, is_unsafe_entry
from src.core.game_data import _JETON_SUR, _est_relatif_sur, _parse_catalog

# Une ligne de valeur d'un .reg : "nom"="chaîne" ou "nom"=dword:xxxxxxxx, où
# une chaîne ne contient que des caractères ordinaires ou des échappements.
_LIGNE_VALEUR = re.compile(
    r'"(?:[^"\\]|\\.)*"=(?:dword:[0-9a-f]{8}|"(?:[^"\\]|\\.)*")')


def _https(url: str) -> bool:
    return url.startswith("https://")


def catalogue(raw: object) -> None:
    """Tout ce qui sort de `_parse_catalog` a passé ses validations.

    Refuser le catalogue entier par `ValueError` est permis (documenté, et
    `load_catalog` retombe sur l'embarqué). Toute AUTRE exception est un
    défaut : elle traverserait `load_catalog` et planterait le démarrage.
    """
    try:
        cat = _parse_catalog(raw)
    except ValueError:
        return

    for jeu in cat.games:
        assert isinstance(jeu.id, str) and jeu.id.strip()
        assert isinstance(jeu.name, str)
        assert _est_relatif_sur(jeu.executable), jeu.executable
        assert jeu.warning_url == "" or _https(jeu.warning_url), jeu.warning_url
        sous = jeu.post_install.sous_dossier
        assert sous == "" or (_JETON_SUR.match(sous) and sous not in (".", "..")), sous
        for version in jeu.versions:
            if version.download_url is not None:
                assert _https(version.download_url), version.download_url
            for part in version.download_parts or ():
                assert _https(part), part

        lr = jeu.language_registry
        if lr is not None:
            for langue in lr.languages:
                assert langue.requires_file == "" or _est_relatif_sur(langue.requires_file)
                valeurs = dict(lr.common) | dict(langue.values)
                # Tout ce que le parseur accepte doit donner un .reg sain, sans
                # que `construire_reg` ait à refuser : sinon le refus arriverait
                # au clic sur JOUER au lieu du chargement du catalogue.
                reg(registre.construire_reg(lr.root, lr.key, valeurs, lr.view),
                    len(valeurs))

    for bande in cat.trailers:
        assert _JETON_SUR.match(bande.game_id) and _JETON_SUR.match(bande.version)
        assert _https(bande.url), bande.url

    for contributeur in cat.contributors:
        assert contributeur.url == "" or _https(contributeur.url), contributeur.url


def reg(texte: str, nb_valeurs: int) -> None:
    """Un .reg produit par le launcher : UNE clé, une ligne par valeur, rien d'autre."""
    lignes = texte.split("\r\n")
    assert lignes[:2] == ["Windows Registry Editor Version 5.00", ""], lignes[:2]
    assert lignes[-1] == ""
    entete, corps = lignes[2], lignes[3:-1]
    assert entete.startswith("[HKEY_") and entete.endswith("]"), entete
    assert "[" not in entete[1:-1] and "]" not in entete[1:-1], entete
    assert len(corps) == nb_valeurs, corps
    for ligne in corps:
        assert _LIGNE_VALEUR.fullmatch(ligne), ligne
    # Aucun saut de ligne d'aucune sorte en dehors des séparateurs CRLF.
    for ligne in lignes:
        assert not any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in ligne), ligne


def registre_ecrit(ruche: str, cle: str, valeurs: dict, vue: int) -> None:
    """`construire_reg` accepte exactement ce que les refus acceptent, et rien
    de ce qu'il produit ne sort de la clé demandée."""
    accepte = registre.refus_de_cle(ruche, cle) is None and all(
        registre.refus_de_valeur(nom, val) is None for nom, val in valeurs.items())
    try:
        texte = registre.construire_reg(ruche, cle, valeurs, vue)
    except ValueError:
        assert not accepte, (ruche, cle, valeurs)
        return
    assert accepte, (ruche, cle, valeurs)
    reg(texte, len(valeurs))


def entree_archive(destination: Path, nom: str) -> None:
    """Une entrée jugée sûre par le filtre rapide (celui du chemin 7z) ne sort
    pas du dossier de destination une fois résolue (Zip Slip)."""
    if "\x00" in nom:
        # 7z ne liste jamais d'octet nul, et `Path` le refuse avant tout usage.
        return
    if not is_unsafe_entry(nom):
        assert check_path_traversal(destination, nom), nom
