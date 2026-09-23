"""Les sept années — lire le catalogue comme une scolarité.

Tout est pur : aucune fixture Qt, aucun manager, aucun disque. C'est le point
du module — l'année vient du catalogue, le reste de deux fonctions passées en
paramètre, donc les cas se FABRIQUENT au lieu de se chercher dans `games.json`.

Le test qui compte le plus est `TestLeQuidditchNeCasseRien` : le catalogue
accueillera peut-être la Coupe du Monde de Quidditch, qui n'est l'année de
personne. Déduire l'année du RANG d'un jeu dans la liste en aurait fait une
« 9ᵉ année » et décalé tout ce qui la suit ; c'est exactement le genre de
raccourci qu'on prend quand rien ne l'interdit.
"""

import dataclasses

from src.core.game_data import GameData, _annee_valide
from src.core.scolarite import (
    ANNEES, Statut, annee_courante, annees, hors_programme,
    prochaine_annee, restantes,
)

_MODELE = GameData(
    id="modele", name="Modèle", year=2001, description="", developer="",
    executable="X/x.exe", cover_image="", tags=(), latest_version="1.0",
    recommended_version="1.0", versions=(),
)


def jeu(id_: str, annee: int) -> GameData:
    return dataclasses.replace(_MODELE, id=id_, annee=annee)


def _sans_rien(_gid):
    return False


def _rien_joue(_gid):
    return 0


class TestLeSqueletteNeDependPasDesDonnees:
    """Sept années, toujours — une année vide est une information."""

    def test_sept_annees_meme_sans_aucun_jeu(self):
        liste = annees([], _sans_rien, _rien_joue)
        assert [a.numero for a in liste] == list(range(1, ANNEES + 1))
        assert all(a.vide for a in liste)
        assert all(a.statut is Statut.ABSENTE for a in liste)

    def test_sept_annees_meme_avec_un_seul_jeu(self):
        liste = annees([jeu("hp3", 3)], _sans_rien, _rien_joue)
        assert len(liste) == ANNEES
        assert [a.numero for a in liste if not a.vide] == [3]


class TestLeQuidditchNeCasseRien:
    """Un jeu hors programme ne décale AUCUNE année."""

    def test_un_jeu_sans_annee_est_hors_programme(self):
        quidditch = jeu("quidditch", 0)
        catalogue = [jeu("hp1", 1), jeu("hp2", 2), quidditch]
        assert hors_programme(catalogue) == [quidditch]

    def test_il_n_apparait_dans_aucune_annee(self):
        catalogue = [jeu("hp1", 1), jeu("quidditch", 0), jeu("hp2", 2)]
        liste = annees(catalogue, _sans_rien, _rien_joue)
        tous = [j.id for a in liste for j in a.jeux]
        assert "quidditch" not in tous
        assert tous == ["hp1", "hp2"]

    def test_il_ne_decale_pas_les_annees_suivantes(self):
        """Posé AU MILIEU du catalogue, là où un calcul par rang ferait le
        plus de dégâts."""
        avec = annees([jeu("hp1", 1), jeu("quidditch", 0), jeu("hp2", 2)],
                      _sans_rien, _rien_joue)
        sans = annees([jeu("hp1", 1), jeu("hp2", 2)], _sans_rien, _rien_joue)
        assert [(a.numero, [j.id for j in a.jeux]) for a in avec] == \
               [(a.numero, [j.id for j in a.jeux]) for a in sans]

    def test_le_temps_passe_dessus_ne_fait_pas_avancer_la_scolarite(self):
        """Jouer cent heures au Quidditch ne fait passer aucune année."""
        catalogue = [jeu("hp1", 1), jeu("quidditch", 0)]
        liste = annees(catalogue, _sans_rien,
                       lambda gid: 360_000 if gid == "quidditch" else 0)
        assert annee_courante(liste) == 0
        assert all(a.secondes == 0 for a in liste)


class TestUneAnneePeutPorterPlusieursJeux:
    """Les deux parties des Reliques sont la MÊME septième année."""

    def test_les_deux_parties_tiennent_dans_la_septieme(self):
        liste = annees([jeu("hp7a", 7), jeu("hp7b", 7)], _sans_rien, _rien_joue)
        septieme = liste[6]
        assert [j.id for j in septieme.jeux] == ["hp7a", "hp7b"]

    def test_le_temps_de_l_annee_est_la_somme_de_ses_jeux(self):
        liste = annees([jeu("hp7a", 7), jeu("hp7b", 7)], _sans_rien,
                       lambda gid: {"hp7a": 100, "hp7b": 50}[gid])
        assert liste[6].secondes == 150


class TestStatut:
    def test_du_temps_de_jeu_vaut_commencee(self):
        liste = annees([jeu("hp1", 1)], _sans_rien, lambda _g: 42)
        assert liste[0].statut is Statut.COMMENCEE

    def test_installe_mais_jamais_lance_vaut_en_attente(self):
        liste = annees([jeu("hp1", 1)], lambda _g: True, _rien_joue)
        assert liste[0].statut is Statut.EN_ATTENTE

    def test_ni_l_un_ni_l_autre_vaut_absente(self):
        liste = annees([jeu("hp1", 1)], _sans_rien, _rien_joue)
        assert liste[0].statut is Statut.ABSENTE

    def test_le_temps_l_emporte_sur_l_installation(self):
        liste = annees([jeu("hp1", 1)], lambda _g: True, lambda _g: 1)
        assert liste[0].statut is Statut.COMMENCEE


class TestAnneeCourante:
    def test_rien_de_joue_vaut_zero(self):
        """0 n'est pas un échec : c'est « la lettre vient d'arriver ». Écrire
        « 1ʳᵉ année » à qui n'a rien lancé serait lui prêter un début."""
        assert annee_courante(annees([jeu("hp1", 1)], lambda _g: True,
                                     _rien_joue)) == 0

    def test_la_plus_haute_commencee_gagne(self):
        """Quelqu'un qui joue HP5 sans avoir touché HP1 est en 5ᵉ année ; le
        renvoyer en première pour un jeu qu'il n'a pas envie de faire serait
        lui décrire une progression qui n'est pas la sienne."""
        catalogue = [jeu("hp1", 1), jeu("hp5", 5)]
        liste = annees(catalogue, _sans_rien,
                       lambda gid: 900 if gid == "hp5" else 0)
        assert annee_courante(liste) == 5

    def test_une_annee_a_deux_jeux_compte_une_fois(self):
        liste = annees([jeu("hp7a", 7), jeu("hp7b", 7)], _sans_rien,
                       lambda gid: 60 if gid == "hp7b" else 0)
        assert annee_courante(liste) == 7


class TestProchaineAnnee:
    """Ce qui ATTEND est DEVANT — jamais une année sautée en chemin."""

    def test_c_est_la_premiere_non_commencee_apres_la_courante(self):
        catalogue = [jeu("hp1", 1), jeu("hp2", 2), jeu("hp3", 3)]
        liste = annees(catalogue, _sans_rien,
                       lambda gid: 60 if gid == "hp1" else 0)
        suivante = prochaine_annee(liste)
        assert suivante is not None and suivante.numero == 2

    def test_une_annee_sautee_n_attend_pas(self):
        """LE cas signalé par Ludo : « Tu es en 7ᵉ année. La 4ᵉ année
        t'attend. » — il l'a qualifié de ridicule, et il avait raison.
        « Attendre » décrit ce qui vient ensuite ; une année manquée derrière
        soi ne vient pas ensuite."""
        catalogue = [jeu(f"hp{n}", n) for n in range(1, 8)]
        joues = {"hp1", "hp2", "hp3", "hp6", "hp7"}
        liste = annees(catalogue, _sans_rien,
                       lambda gid: 60 if gid in joues else 0)
        assert annee_courante(liste) == 7
        assert prochaine_annee(liste) is None
        assert [a.numero for a in restantes(liste)] == [4, 5]

    def test_une_annee_vide_n_est_jamais_proposee(self):
        """Proposer une année qu'aucun jeu ne raconte serait envoyer quelqu'un
        vers une porte fermée."""
        liste = annees([jeu("hp2", 2), jeu("hp4", 4)], _sans_rien,
                       lambda gid: 60 if gid == "hp2" else 0)
        suivante = prochaine_annee(liste)
        assert suivante is not None and suivante.numero == 4

    def test_rien_a_proposer_quand_tout_a_commence(self):
        catalogue = [jeu("hp1", 1), jeu("hp2", 2)]
        liste = annees(catalogue, _sans_rien, lambda _g: 60)
        assert prochaine_annee(liste) is None
        assert restantes(liste) == []

    def test_restantes_ne_compte_que_les_annees_qui_ont_un_jeu(self):
        liste = annees([jeu("hp1", 1), jeu("hp5", 5)], _sans_rien,
                       lambda gid: 60 if gid == "hp1" else 0)
        assert [a.numero for a in restantes(liste)] == [5]


class TestLAnneeVientDuCatalogueEtEstValidee:
    """Le catalogue est DISTANT : ce champ arrive du réseau."""

    def test_une_annee_hors_bornes_vaut_hors_programme(self):
        assert _annee_valide(0) == 0
        assert _annee_valide(8) == 0
        assert _annee_valide(-3) == 0

    def test_un_booleen_n_est_pas_une_annee(self):
        """`True` EST un `int` en Python : sans refus explicite, un
        `"annee": true` dans le catalogue vaudrait « 1ʳᵉ année »."""
        assert _annee_valide(True) == 0
        assert _annee_valide(False) == 0

    def test_ce_qui_n_est_pas_un_entier_est_refuse(self):
        for valeur in ("3", 3.0, None, [3], {"annee": 3}):
            assert _annee_valide(valeur) == 0

    def test_les_bornes_sont_acceptees(self):
        assert _annee_valide(1) == 1
        assert _annee_valide(ANNEES) == ANNEES

    def test_le_champ_survit_au_parsing_complet(self):
        données = {
            "id": "hp4", "name": "X", "year": 2005, "description": "",
            "developer": "KnowWonder", "executable": "HP4/hp4.exe",
            "cover_image": "hp4.jpg",
            "annee": 4,
        }
        assert GameData.from_dict(données).annee == 4

    def test_un_jeu_sans_le_champ_est_hors_programme(self):
        """Le cas du Quidditch, et celui de tout catalogue plus ancien."""
        données = {
            "id": "quidditch", "name": "X", "year": 2002, "description": "",
            "developer": "EA", "executable": "Q/q.exe",
            "cover_image": "q.jpg",
        }
        assert GameData.from_dict(données).annee == 0
