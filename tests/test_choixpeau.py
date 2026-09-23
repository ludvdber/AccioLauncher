"""Le Choixpeau : une règle, pas un tirage.

Ludo, 2026-09-19 : « Le Choixpeau au premier lancement est une excellente
idée. » Ce fichier garde ce qui rendrait le moment faux — du hasard, une
maison inatteignable, ou un questionnaire qu'on résout sans le lire.
"""
import itertools

import pytest

from src.core.choixpeau import (
    GRYFFONDOR, MAISONS, POUFSOUFFLE, QUESTIONS, SERDAIGLE, SERPENTARD,
    question, repartir, reponses, verdict,
)


class TestLaRegle:
    def test_repartir_est_deterministe(self):
        """Recommencer en répondant pareil doit redonner la même maison.

        Un Choixpeau qui tire au sort serait un bouton « thème aléatoire »
        déguisé : le moment ne voudrait plus rien dire.
        """
        choix = [0, 2, 1, 3]
        assert len({repartir(choix) for _ in range(50)}) == 1

    def test_repondre_toujours_la_meme_maison_y_mene(self):
        for maison in MAISONS:
            choix = [
                next(i for i, (_, m) in enumerate(options) if m == maison)
                for _, options in QUESTIONS
            ]
            assert repartir(choix) == maison, maison

    def test_les_quatre_maisons_sont_atteignables(self):
        """Une maison qu'aucune combinaison ne peut donner serait un décor.

        On balaye TOUTES les combinaisons possibles (4^4 = 256).
        """
        tirees = {repartir(list(c)) for c in
                  itertools.product(range(4), repeat=len(QUESTIONS))}
        assert set(MAISONS) <= tirees

    def test_aucune_reponse_ne_repartit_personne(self):
        """`-1` est ce que rend un QButtonGroup sans coche.

        Inventer une maison à qui n'a rien répondu serait mentir sur ce qu'il
        a fait — l'assistant garde alors le thème de Poudlard.
        """
        assert repartir([]) == ""
        assert repartir([-1, -1, -1, -1]) == ""

    def test_les_reponses_hors_bornes_sont_ignorees_pas_refusees(self):
        """Lever une exception au milieu du premier lancement serait la pire
        façon de commencer."""
        gryffondor = next(i for i, (_, m) in enumerate(QUESTIONS[0][1])
                          if m == GRYFFONDOR)
        assert repartir([gryffondor, 99, None, -1]) == GRYFFONDOR

    def test_la_derniere_question_pese_double(self):
        """Elle demande ce qu'on veut LAISSER : elle départage mieux que trois
        situations, et rend les égalités rares."""
        def rang(q, maison):
            return next(i for i, (_, m) in enumerate(QUESTIONS[q][1])
                        if m == maison)
        # Une voix pour Serdaigle sur Q1, une pour Serpentard sur Q4 (×2).
        choix = [rang(0, SERDAIGLE), -1, -1, rang(3, SERPENTARD)]
        assert repartir(choix) == SERPENTARD

    def test_une_egalite_revient_au_premier_choix(self):
        """La seule règle qui reste explicable à voix haute."""
        def rang(q, maison):
            return next(i for i, (_, m) in enumerate(QUESTIONS[q][1])
                        if m == maison)
        # Q2 Poufsouffle puis Q3 Serdaigle : 1 point chacune, Poufsouffle
        # d'abord. (Q1 et Q4 sans réponse.)
        assert repartir([-1, rang(1, POUFSOUFFLE), rang(2, SERDAIGLE), -1]) \
            == POUFSOUFFLE
        # Inversé : c'est Serdaigle qui a été choisie en premier.
        assert repartir([-1, rang(1, SERDAIGLE), rang(2, POUFSOUFFLE), -1]) \
            == SERDAIGLE


class TestLeQuestionnaire:
    def test_chaque_question_propose_les_quatre_maisons(self):
        for index, (_, options) in enumerate(QUESTIONS):
            assert {m for _, m in options} == set(MAISONS), index

    def test_la_position_des_reponses_change_d_une_question_a_l_autre(self):
        """Quatre questions dont la première réponse mène toujours à
        Gryffondor, c'est un questionnaire qu'on résout sans le lire."""
        premieres = [options[0][1] for _, options in QUESTIONS]
        assert len(set(premieres)) > 1

    def test_les_textes_passent_par_la_traduction(self):
        """`tr()` est appelé À L'APPEL : la langue est choisie à l'écran 1,
        donc après l'import de ce module."""
        from src.core.i18n import set_language
        set_language("en")
        try:
            assert "corridor" in question(0).lower()
            assert any("library" in r.lower() for r in reponses(0))
            assert "GRYFFINDOR" in verdict(GRYFFONDOR)
        finally:
            set_language("fr")

    def test_toutes_les_reponses_sont_distinctes(self):
        for index, (_, options) in enumerate(QUESTIONS):
            textes = [t for t, _ in options]
            assert len(set(textes)) == len(textes), index


@pytest.mark.parametrize("maison", MAISONS)
def test_chaque_maison_a_son_verdict(maison):
    assert verdict(maison).strip()
