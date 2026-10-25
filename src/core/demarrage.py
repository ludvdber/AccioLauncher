"""Les étapes du démarrage, annoncées par ceux qui les font.

Maquette « Démarrage A » validée par Ludo le 2026-10-14 : une ligne de
progression qui nomme ses étapes. Elles ne sont dites qu'au moment où le travail
commence VRAIMENT (règle 123, et `main.py` : « rien n'est simulé »). Le
catalogue et vos jeux se font dans `GameManager`, la bibliothèque dans
`MainWindow`, la fenêtre dans `main.py` : chacun annonce la sienne ici, et
l'écran de démarrage écoute. Sans écran (tests, assistant), personne n'écoute
et l'annonce ne coûte rien.

Pas de bandes-annonces dans la liste, contrairement à la maquette : elles se
téléchargent APRÈS l'ouverture, en arrière-plan, et c'est la barre du bas qui
le dit. Les annoncer au démarrage serait dire un travail qui n'a pas lieu.
"""

from collections.abc import Callable

CATALOGUE = "catalogue"
JEUX = "jeux"
BIBLIOTHEQUE = "bibliotheque"
FENETRE = "fenetre"

# L'ordre de la ligne à l'écran.
ETAPES = (CATALOGUE, JEUX, BIBLIOTHEQUE, FENETRE)

_auditeur: Callable[[str], None] | None = None


def ecouter(auditeur: Callable[[str], None] | None) -> None:
    """Un seul auditeur : l'écran de démarrage. None le retire."""
    global _auditeur
    _auditeur = auditeur


def annoncer(etape: str) -> None:
    """`etape` commence. Une étape inconnue ou sans auditeur ne fait rien."""
    if _auditeur is not None and etape in ETAPES:
        _auditeur(etape)
