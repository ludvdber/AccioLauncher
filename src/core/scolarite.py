"""Les sept années — lire le catalogue comme une scolarité.

Aucun autre launcher ne peut faire ça, parce que ça ne marche que sur CE
catalogue : sept jeux, sept années, dans l'ordre. La bibliothèque cesse d'être
une grille de produits et devient un parcours — « vous êtes en 3ᵉ année », un
jeu jamais lancé est une année qui vous attend.

**Aucune donnée nouvelle n'est collectée.** Tout se déduit de ce que le
launcher mesure déjà : l'année vient du catalogue (`GameData.annee`), le reste
de l'état d'installation et du temps de jeu. C'est une LECTURE, pas un
mécanisme de plus.

Trois décisions qui tiennent tout le module :

① **L'année vient du catalogue, jamais du rang du jeu dans la liste.** Le
catalogue accueillera peut-être la Coupe du Monde de Quidditch, qui n'est
l'année de personne : déduire l'année d'un index en aurait fait une « 9ᵉ
année » et aurait décalé tout ce qui la suit. Sans `annee`, un jeu est
simplement hors des cours, et la scolarité ne bouge pas.

② **Une année peut porter plusieurs jeux.** Les deux parties des Reliques de la
Mort sont la même septième année, celle qui ne s'est pas passée à Poudlard.

③ **On ne prétend pas savoir qu'un jeu est TERMINÉ.** Le launcher ne le sait
pas — il n'y a ni succès ni lecture des sauvegardes aujourd'hui. L'année en
cours est donc la plus haute année COMMENCÉE, ce qui est observable et vrai.
Le jour où la progression se lira dans les sauvegardes ([[project_saves_
progression]]), `annee_courante` en tiendra compte sans que l'affichage change.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Sequence

from src.core.game_data import GameData

# Nombre d'années d'une scolarité à Poudlard. Sert de squelette d'affichage :
# les sept années existent même quand aucun jeu ne les remplit — une année
# vide est une information (« elle vous attend »), pas une absence à masquer.
ANNEES = 7


class Statut(StrEnum):
    """Où en est une année. Jamais « terminée » : on ne le sait pas."""

    ABSENTE = "absente"        # aucun jeu installé, jamais joué
    EN_ATTENTE = "en_attente"  # installé, jamais lancé — « elle vous attend »
    COMMENCEE = "commencee"    # du temps de jeu enregistré


@dataclass(frozen=True)
class Annee:
    """Une année de scolarité, et les jeux qui la racontent."""

    numero: int
    jeux: tuple[GameData, ...]
    statut: Statut
    secondes: int

    @property
    def vide(self) -> bool:
        """Aucun jeu du catalogue ne porte cette année."""
        return not self.jeux


def _statut(jeux: Sequence[GameData], installe, secondes: int) -> Statut:
    if secondes > 0:
        return Statut.COMMENCEE
    if any(installe(j.id) for j in jeux):
        return Statut.EN_ATTENTE
    return Statut.ABSENTE


def annees(games: Iterable[GameData], installe, temps) -> list[Annee]:
    """Les sept années, dans l'ordre, remplies par le catalogue.

    `installe(game_id) -> bool` et `temps(game_id) -> int` (secondes) sont
    passés EXPLICITEMENT plutôt que lus sur un `GameManager` : le module reste
    pur, donc exerçable sans construire un manager, une config ni un disque.
    C'est la même leçon que `game_language`, extrait pour la même raison.
    """
    par_annee: dict[int, list[GameData]] = {n: [] for n in range(1, ANNEES + 1)}
    for jeu in games:
        if 1 <= jeu.annee <= ANNEES:
            par_annee[jeu.annee].append(jeu)

    resultat = []
    for numero in range(1, ANNEES + 1):
        jeux = tuple(par_annee[numero])
        secondes = sum(temps(j.id) for j in jeux)
        resultat.append(Annee(numero=numero, jeux=jeux,
                              statut=_statut(jeux, installe, secondes),
                              secondes=secondes))
    return resultat


def hors_programme(games: Iterable[GameData]) -> list[GameData]:
    """Les jeux que le catalogue ne rattache à aucune année.

    Aucun aujourd'hui. Le jour où la Coupe du Monde de Quidditch arrive, elle
    se range ici sans qu'une ligne change — c'est précisément ce que cette
    fonction existe pour garantir.
    """
    return [j for j in games if not 1 <= j.annee <= ANNEES]


def annee_courante(liste: Sequence[Annee]) -> int:
    """L'année où l'on se trouve : la plus haute qui soit COMMENCÉE, sinon 0.

    0 n'est pas un échec, c'est « la lettre vient d'arriver ». Afficher « 1ʳᵉ
    année » à quelqu'un qui n'a encore rien lancé serait lui prêter un début
    qu'il n'a pas eu.

    La plus HAUTE et non la première non commencée : quelqu'un qui joue HP5
    sans avoir touché HP1 est en 5ᵉ année. Le contraire le renverrait en
    première pour un jeu qu'il n'a pas envie de faire.
    """
    return max((a.numero for a in liste if a.statut is Statut.COMMENCEE),
               default=0)


def restantes(liste: Sequence[Annee]) -> list[Annee]:
    """Les années qui ont un jeu et qu'on n'a pas commencées."""
    return [a for a in liste if a.statut is not Statut.COMMENCEE and not a.vide]


def prochaine_annee(liste: Sequence[Annee]) -> Annee | None:
    """La prochaine année à commencer — celle qui est DEVANT, jamais derrière.

    « Tu es en 7ᵉ année. La 4ᵉ année t'attend. » : c'est la première version,
    et Ludo l'a qualifiée de ridicule le 2026-09-23. Il avait raison. « Attendre »
    décrit ce qui vient ensuite ; une année sautée en chemin n'attend pas, elle
    manque. Le défaut venait de « la première non commencée », qui regarde la
    liste depuis le début au lieu de regarder depuis OÙ L'ON EST.

    None quand il n'y a plus rien devant — soit tout est commencé, soit les
    années qui restent sont derrière, et c'est alors `restantes()` qui a
    quelque chose à dire.
    """
    courante = annee_courante(liste)
    for annee in liste:
        if (annee.numero > courante and annee.statut is not Statut.COMMENCEE
                and not annee.vide):
            return annee
    return None
