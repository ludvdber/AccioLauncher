"""Quelles illustrations du launcher attendent un artiste (2026-10-09).

Les images viennent d'où elles ont pu : des fonds de 849 px de large étirés
sur un écran de 2560, des jaquettes CARRÉES dans un carrousel en portrait. Le
launcher les rend au mieux (`src/ui/images.py`), mais le vrai remède est une
illustration faite pour lui. Cette règle dit lesquelles, d'après leurs
dimensions : l'atelier (`atelier.py`) en tire son métier « Jaquettes et
fonds », qui se met donc à jour tout seul à mesure que les images arrivent.

Les cibles sont celles du cahier des charges envoyé aux artistes : jaquette
1080 × 1500 (le rapport 18:25 des vignettes du carrousel), fond 3840 × 2160.
"""

JAQUETTE = (1080, 1500)
FOND = (3840, 2160)
# En dessous, l'image est agrandie au-delà de ce qui reste net sur un écran
# Full HD : un fond plus étroit que l'écran, une jaquette sous 900 px de haut
# affichée à 250 px physiques sur un écran à 125 % puis zoomée au survol.
FOND_LARGEUR_MIN = 1920
JAQUETTE_HAUTEUR_MIN = 900
# Au-delà de cet écart de proportions, recadrer coupe le sujet : une jaquette
# carrée perd un tiers de sa largeur dans une vignette en portrait.
ECART_PROPORTIONS = 0.12


def jaquette_a_refaire(largeur: int, hauteur: int) -> bool:
    if largeur <= 0 or hauteur <= 0:
        return True
    cible = JAQUETTE[0] / JAQUETTE[1]
    return hauteur < JAQUETTE_HAUTEUR_MIN or abs(largeur / hauteur - cible) / cible > ECART_PROPORTIONS


def fond_a_refaire(largeur: int, hauteur: int) -> bool:
    return largeur < FOND_LARGEUR_MIN or hauteur <= 0


def a_refaire(tailles: dict[str, tuple[tuple[int, int], tuple[int, int]]]) -> list[tuple[str, str]]:
    """[(id du jeu, « jaquette » | « fond »)], dans l'ordre du catalogue.

    `tailles` : id → ((largeur, hauteur) de la jaquette, (largeur, hauteur) du fond).
    """
    besoins: list[tuple[str, str]] = []
    for jeu, (jaquette, fond) in tailles.items():
        if jaquette_a_refaire(*jaquette):
            besoins.append((jeu, "jaquette"))
        if fond_a_refaire(*fond):
            besoins.append((jeu, "fond"))
    return besoins
