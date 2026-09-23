"""Le fait du jour — ce que l'Almanach a à dire aujourd'hui.

Module PUR : une table de dates, une table de faits, et la règle qui choisit.
Aucun Qt, aucun réseau, aucun état.

**Toutes les dates sont canoniques et ont été VÉRIFIÉES** (Harry Potter Lexicon
et chronologies concordantes, relevé du 2026-09-23) — pas récitées de mémoire.
Un almanach qui se trompe de date est pire qu'un almanach vide : il apprend
quelque chose de faux à quelqu'un qui fait confiance au launcher. Quand une
date est discutée entre sources, elle n'entre pas dans la table.

**Où ça s'affiche** : dans la barre de statut, à la place de « Prêt ». C'est un
double gain — le projet s'interdit d'afficher un état NORMAL (« Prêt » n'apprend
rien à personne et occupait cette ligne en permanence), et le fait du jour
occupe une place qui existait déjà, sans coûter un pixel de hauteur. Tout
message réel — téléchargement, mise à jour disponible, hors ligne — passe
devant : le fait ne s'affiche que quand le launcher n'a rien d'autre à dire.
C'est ce qui le rend non intrusif au sens où Ludo le demandait.

La règle de choix, dans l'ordre :

1. **Une date exacte** l'emporte sur tout — le 31 juillet, c'est l'anniversaire
   de Harry, pas un fait au hasard.
2. **Sinon, un fait DE SAISON** : en septembre on parle de rentrée, en octobre
   d'Halloween. C'est ce qui donne « c'est le mois de la rentrée à Poudlard »
   sans répéter la même phrase vingt-huit jours de suite.
3. **Sinon, le fonds commun.**

Le tirage est déterministe (quantième de l'année) et non aléatoire : le fait
change chaque jour mais ne change pas en cours de journée, ni entre deux
lancements. Un fait qui saute à chaque ouverture du launcher est du bruit, pas
un almanach.
"""

from dataclasses import dataclass
from datetime import date

from src.core.season import current_season


@dataclass(frozen=True)
class Fait:
    """Un fait, et la saison à laquelle il appartient (vide = toute l'année)."""

    texte: str
    saison: str = ""


# ── Les dates exactes ────────────────────────────────────────────────────
# (mois, jour) → texte. Les textes sont des clés de traduction : ils doivent
# exister dans chaque `src/data/i18n/*.json`, comme les noms de maison.
FAITS_DATES: dict[tuple[int, int], str] = {
    (1, 9): "Aujourd'hui, en 1960, naissait Severus Rogue.",
    (2, 13): "Aujourd'hui, c'est l'anniversaire de Luna Lovegood.",
    (3, 1): "Aujourd'hui, en 1980, naissait Ron Weasley.",
    (3, 10): "Aujourd'hui, vers 1960, naissait Remus Lupin.",
    (5, 2): "Le 2 mai 1998, la bataille de Poudlard prenait fin.",
    (5, 29): "Le 29 mai 1993, Harry affrontait le Basilic dans la Chambre des Secrets.",
    (6, 5): "Aujourd'hui, en 1980, naissait Drago Malefoy.",
    (6, 18): "Le 18 juin 1996, Sirius Black tombait au Département des mystères.",
    (6, 30): "Le 30 juin 1997, Dumbledore mourait en haut de la tour d'astronomie.",
    (7, 30): "Aujourd'hui, en 1980, naissait Neville Londubat.",
    (7, 31): "Aujourd'hui, en 1980, naissait Harry Potter.",
    (8, 11): "Aujourd'hui, en 1981, naissait Ginny Weasley.",
    (8, 26): "Aujourd'hui, c'est l'anniversaire de Dolores Ombrage.",
    (9, 1): "Le 1ᵉʳ septembre, le Poudlard Express quitte la voie 9¾ à onze heures précises.",
    (9, 19): "Aujourd'hui, en 1979, naissait Hermione Granger.",
    (10, 4): "Aujourd'hui, vers 1935, naissait Minerva McGonagall.",
    (10, 31): "Le 31 octobre 1981, James et Lily Potter mouraient à Godric's Hollow.",
    (11, 3): "Aujourd'hui, c'est l'anniversaire de Sirius Black.",
    (12, 6): "Aujourd'hui, en 1928, naissait Rubeus Hagrid.",
    (12, 31): "Aujourd'hui, en 1926, naissait Tom Elvis Jedusor.",
}

# ── Le fonds commun, par saison ──────────────────────────────────────────
FAITS: tuple[Fait, ...] = (
    # — Rentrée (septembre) —
    Fait("C'est le mois de la rentrée à Poudlard.", "rentree"),
    Fait("La voie 9¾ se trouve entre les voies 9 et 10 de la gare de King's Cross.",
         "rentree"),
    Fait("Le Choixpeau chante une chanson différente à chaque rentrée.", "rentree"),
    Fait("Les première année traversent le lac en barque ; les autres prennent "
         "les diligences.", "rentree"),
    # — Halloween (octobre) —
    Fait("Au festin d'Halloween, des centaines de chauves-souris volent dans la "
         "Grande Salle.", "halloween"),
    Fait("C'est un soir d'Halloween qu'un troll est entré dans le château.",
         "halloween"),
    Fait("Nick Quasi-Sans-Tête fête chaque année l'anniversaire de sa mort, "
         "un 31 octobre.", "halloween"),
    # — Noël (décembre) —
    Fait("À Noël, douze sapins décorent la Grande Salle.", "noel"),
    Fait("Harry a reçu sa cape d'invisibilité à Noël, sans savoir de qui.", "noel"),
    Fait("Le Miroir du Riséd montre le plus profond désir de celui qui s'y "
         "regarde.", "noel"),
    # — Anniversaire (juillet) —
    Fait("Hagrid a apporté à Harry un gâteau d'anniversaire un peu écrasé, "
         "pour ses onze ans.", "anniversaire"),
    Fait("Harry a appris qu'il était sorcier la veille de ses onze ans.",
         "anniversaire"),
    # — Bataille (mai) —
    Fait("Les statues du château se sont battues aux côtés des élèves.", "bataille"),
    Fait("« Toujours. » — la réponse de Rogue à Dumbledore.", "bataille"),
    # — Toute l'année —
    Fait("Poudlard compte quatre maisons et sept années d'études."),
    Fait("Il existe trois Sortilèges Impardonnables."),
    Fait("Attraper le Vif d'or rapporte cent cinquante points et met fin au match."),
    Fait("La Carte du Maraudeur s'ouvre sur « Je jure solennellement que mes "
         "intentions sont mauvaises »."),
    Fait("Pour effacer la Carte du Maraudeur : « Méfait accompli »."),
    Fait("Les Reliques de la Mort sont la Baguette de Sureau, la Pierre de "
         "Résurrection et la Cape d'Invisibilité."),
    Fait("Alohomora ouvre les portes ; Lumos allume le bout de la baguette."),
    Fait("Un Épouvantard prend la forme de ce que l'on craint le plus."),
    Fait("Les escaliers de Poudlard changent de place quand ça leur chante."),
    Fait("On ne transplane pas dans l'enceinte de Poudlard."),
)


def fait_du_jour(today: date | None = None) -> str:
    """Le fait à afficher aujourd'hui, ou une chaîne vide s'il n'y en a pas.

    Déterministe : le même jour rend toujours le même fait. Un almanach qui
    change à chaque ouverture du launcher n'est pas un almanach.
    """
    today = today or date.today()
    exact = FAITS_DATES.get((today.month, today.day))
    if exact:
        return exact

    saison = current_season(today)
    candidats = [f.texte for f in FAITS if f.saison == saison]
    if not candidats:
        candidats = [f.texte for f in FAITS if not f.saison]
    if not candidats:
        return ""
    return candidats[today.timetuple().tm_yday % len(candidats)]


def tous_les_textes() -> list[str]:
    """Tous les faits, pour la couverture de traduction et les tests."""
    return sorted({*FAITS_DATES.values(), *(f.texte for f in FAITS)})
