"""Ce que l'assistant de premier lancement doit encore montrer.

Beaucoup ont installé Accio avant que l'assistant ne pose le Choixpeau et la
question des bandes-annonces : à chaque mise à jour, leur config existe déjà,
l'assistant ne revient jamais, et ils ne découvrent ni leur maison ni les
vidéos (Ludo, 2026-10-09). On ne leur refait pas tout : seulement les étapes
jamais vues, une fois.

`Config.etapes_assistant` liste celles qui ONT été montrées. Une config neuve
les porte toutes ; une config d'avant la 1.1.6 se charge sans la clé, donc
vide, et c'est ce qui la désigne.
"""
from __future__ import annotations

from collections.abc import Iterable

from src.core.choixpeau import MAISONS

CHOIXPEAU = "choixpeau"
TOUCHES = "touches"
# Dans l'ordre où l'assistant les montre.
ETAPES_RATTRAPABLES = (CHOIXPEAU, TOUCHES)


def etapes_a_rattraper(vues: Iterable[str], theme: str, trailers_optin: bool) -> tuple[str, ...]:
    """Les étapes à montrer à quelqu'un qui a déjà le launcher, dans l'ordre.

    - le Choixpeau, si aucune maison n'a été choisie : un thème de maison dit
      que la question a déjà trouvé sa réponse, par l'assistant ou à la main ;
    - les dernières touches (couleurs, bandes-annonces), si le Choixpeau
      revient (sa maison se choisit là) ou si les bandes-annonces n'ont jamais
      été acceptées. `trailers_optin` faux ne distingue pas « non » de
      « jamais demandé » : on repose la question UNE fois, c'est tout.
    """
    vues = set(vues)
    choixpeau = CHOIXPEAU not in vues and theme not in MAISONS
    touches = TOUCHES not in vues and (choixpeau or not trailers_optin)
    return tuple(e for e, montree in ((CHOIXPEAU, choixpeau), (TOUCHES, touches)) if montree)
