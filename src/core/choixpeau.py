"""Le Choixpeau : quatre questions, une maison.

Pourquoi ici et pas dans l'interface : la répartition est une RÈGLE, pas un
écran. Elle se teste sans Qt, elle se relit, et le jour où l'on voudra la
rejouer depuis les Paramètres, il n'y aura rien à déplacer.

**Aucun hasard.** Un Choixpeau qui tire au sort serait un bouton « thème
aléatoire » déguisé, et quelqu'un qui recommence en répondant pareil doit
retomber sur la même maison — sinon le moment ne veut rien dire. `repartir`
est une fonction PURE de ses réponses.

Les textes passent par `tr()` À L'APPEL et non à l'import : la langue est
choisie à l'écran 1 de l'assistant, donc APRÈS le chargement de ce module.
"""
from __future__ import annotations

from collections.abc import Sequence

from src.core.i18n import tr

# Les identifiants sont ceux des thèmes (`src/ui/theme.py`) : la maison tirée
# devient le thème proposé, sans table de correspondance à tenir à jour.
GRYFFONDOR = "gryffondor"
SERPENTARD = "serpentard"
SERDAIGLE = "serdaigle"
POUFSOUFFLE = "poufsouffle"

MAISONS = (GRYFFONDOR, SERPENTARD, SERDAIGLE, POUFSOUFFLE)

# (question, ((réponse, maison), ...)). L'ordre des réponses CHANGE d'une
# question à l'autre : quatre questions dont la première réponse mène toujours
# à Gryffondor, c'est un questionnaire qu'on résout sans le lire.
QUESTIONS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Un couloir interdit, une porte entrouverte. Que faites-vous ?",
        (
            ("J'entre. On verra bien.", GRYFFONDOR),
            ("Je retiens l'endroit et je reviens préparé.", SERPENTARD),
            ("Je cherche d'abord ce que la bibliothèque en dit.", SERDAIGLE),
            ("Je vais chercher quelqu'un, on n'y va pas seul.", POUFSOUFFLE),
        ),
    ),
    (
        "Votre chaudron déborde à dix minutes de la fin du cours.",
        (
            ("Je comprends d'abord pourquoi avant de toucher à quoi que ce soit.",
             SERDAIGLE),
            ("Je recommence depuis le début, tant pis pour l'heure.", POUFSOUFFLE),
            ("Je le rattrape à l'instinct, ça tiendra.", GRYFFONDOR),
            ("J'échange discrètement avec le chaudron d'à côté.", SERPENTARD),
        ),
    ),
    (
        "Qu'est-ce qui serait le pire ?",
        (
            ("Qu'on me croie déloyal.", POUFSOUFFLE),
            ("Qu'on me croie lâche.", GRYFFONDOR),
            ("Qu'on me croie insignifiant.", SERPENTARD),
            ("Qu'on me croie idiot.", SERDAIGLE),
        ),
    ),
    (
        "Dans dix ans, on se souviendra de vous pour…",
        (
            ("ce que vous avez bâti.", SERPENTARD),
            ("ceux que vous n'avez pas lâchés.", POUFSOUFFLE),
            ("ce que vous avez osé.", GRYFFONDOR),
            ("ce que vous avez compris.", SERDAIGLE),
        ),
    ),
)

# La dernière question pèse double : elle demande ce qu'on veut LAISSER, ce qui
# départage mieux que trois situations. Elle rend aussi les égalités rares.
_POIDS = (1, 1, 1, 2)

_VERDICTS = {
    GRYFFONDOR: "Du cran, du nerf, et le goût de passer la porte en premier. "
                "GRYFFONDOR !",
    SERPENTARD: "De l'ambition, et la patience qu'il faut pour la servir. "
                "SERPENTARD !",
    SERDAIGLE: "Un esprit qui veut comprendre avant d'agir. SERDAIGLE !",
    POUFSOUFFLE: "De la loyauté, et le courage plus rare de rester. "
                 "POUFSOUFFLE !",
}


def question(index: int) -> str:
    """Intitulé traduit de la question `index`."""
    return tr(QUESTIONS[index][0])


def reponses(index: int) -> tuple[str, ...]:
    """Réponses traduites de la question `index`, dans l'ordre d'affichage."""
    return tuple(tr(texte) for texte, _ in QUESTIONS[index][1])


def verdict(maison: str) -> str:
    """Ce que le Choixpeau annonce à voix haute."""
    return tr(_VERDICTS[maison])


def repartir(choix: Sequence[int]) -> str:
    """Rend la maison correspondant aux réponses données, dans l'ordre.

    `choix[i]` est l'index de la réponse retenue à la question `i`. Les
    réponses manquantes ou hors bornes sont IGNORÉES plutôt que refusées :
    l'assistant doit pouvoir répartir quelqu'un qui s'arrête en route, et
    lever une exception au milieu du premier lancement serait la pire façon
    de commencer.

    **Égalité** : la maison choisie le PLUS TÔT l'emporte. C'est la seule
    règle qui reste explicable à voix haute — « votre premier réflexe a
    tranché » — et elle est déterministe, contrairement à un tirage.
    """
    points = dict.fromkeys(MAISONS, 0)
    premier_vote: dict[str, int] = {}
    for i, index in enumerate(choix):
        if i >= len(QUESTIONS):
            break
        options = QUESTIONS[i][1]
        if not isinstance(index, int) or not 0 <= index < len(options):
            continue
        maison = options[index][1]
        points[maison] += _POIDS[i]
        premier_vote.setdefault(maison, i)

    if not premier_vote:
        # Personne n'a répondu : aucune maison n'a été choisie, et en inventer
        # une serait mentir sur ce que l'utilisateur a fait.
        return ""
    meilleur = max(points.values())
    exaequo = [m for m in MAISONS if points[m] == meilleur and m in premier_vote]
    return min(exaequo, key=lambda m: premier_vote[m])
