"""Le fait du jour — l'Almanach a-t-il quelque chose à dire, et est-ce vrai ?

Demandé par Ludo le 2026-09-23 : « des fun facts quelque part dans un coin…
désactivable dans les paramètres mais pas intrusif ».

Le test qui compte le plus est `TestChaqueFaitEstTraduit` : ces textes passent
par `tr()` À L'APPEL (`tr(fait)`), donc l'extracteur AST de `test_i18n.py` ne
les voit pas et ne peut pas réclamer leur traduction. Sans ce filet, un fait
ajouté resterait en français au milieu d'une interface anglaise, et RIEN ne le
signalerait.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from src.core.almanach import FAITS, FAITS_DATES, fait_du_jour, tous_les_textes
from src.core.season import SEASONS, current_season

LANGUES = sorted((Path(__file__).resolve().parents[1]
                  / "src" / "data" / "i18n").glob("*.json"))


class TestIlYAToujoursQuelqueChoseADire:
    def test_chaque_jour_de_l_annee_rend_un_fait(self):
        """Une barre de statut vide un jour sur deux serait pire que « Prêt »."""
        jour = date(2026, 1, 1)
        while jour.year == 2026:
            assert fait_du_jour(jour), jour
            jour += timedelta(days=1)

    def test_une_annee_bissextile_ne_troue_pas_l_almanach(self):
        assert fait_du_jour(date(2028, 2, 29))


class TestLeChoixEstDeterministe:
    """Un fait qui saute à chaque ouverture du launcher est du bruit."""

    def test_le_meme_jour_rend_toujours_le_meme_fait(self):
        jour = date(2026, 4, 12)
        assert len({fait_du_jour(jour) for _ in range(50)}) == 1

    def test_deux_jours_voisins_ne_disent_pas_la_meme_chose(self):
        """Sinon l'almanach paraît figé — et on cesse de le lire."""
        base = date(2026, 3, 15)
        vus = [fait_du_jour(base + timedelta(days=i)) for i in range(5)]
        assert len(set(vus)) >= 4, vus


class TestUneDateExacteLEmporte:
    def test_le_31_juillet_parle_de_harry(self):
        assert fait_du_jour(date(2026, 7, 31)) == FAITS_DATES[(7, 31)]

    def test_le_2_mai_parle_de_la_bataille(self):
        assert fait_du_jour(date(2026, 5, 2)) == FAITS_DATES[(5, 2)]

    def test_toutes_les_dates_de_la_table_sont_servies(self):
        """Une date qu'un fait de saison masquerait serait une date écrite
        pour rien."""
        for (mois, jour), texte in FAITS_DATES.items():
            assert fait_du_jour(date(2026, mois, jour)) == texte, (mois, jour)

    def test_les_dates_de_la_table_existent_vraiment(self):
        """`(2, 30)` passerait inaperçu jusqu'au jour où personne ne le voit."""
        for mois, jour in FAITS_DATES:
            date(2028, mois, jour)          # 2028 est bissextile


class TestLesFaitsSuiventLaSaison:
    """« C'est le mois de la rentrée à Poudlard » — sans répéter la même
    phrase vingt-huit jours de suite."""

    def test_en_octobre_on_parle_d_halloween(self):
        attendus = {f.texte for f in FAITS if f.saison == "halloween"}
        vus = {fait_du_jour(date(2026, 10, j)) for j in range(2, 30)
               if (10, j) not in FAITS_DATES}
        assert vus and vus <= attendus

    def test_en_septembre_on_parle_de_la_rentree(self):
        attendus = {f.texte for f in FAITS if f.saison == "rentree"}
        vus = {fait_du_jour(date(2026, 9, j)) for j in range(2, 19)}
        assert vus and vus <= attendus

    def test_hors_saison_on_puise_dans_le_fonds_commun(self):
        commun = {f.texte for f in FAITS if not f.saison}
        vus = {fait_du_jour(date(2026, 4, j)) for j in range(1, 29)}
        assert vus <= commun

    def test_chaque_saison_a_de_quoi_parler(self):
        """Une saison sans fait retomberait sur le fonds commun sans le dire —
        et « c'est le mois de la rentrée » ne serait jamais affiché."""
        for saison in SEASONS:
            if saison in ("auto", "aucune"):
                continue
            assert any(f.saison == saison for f in FAITS), saison


class TestChaqueFaitEstTraduit:
    """`tr(fait)` est résolu À L'APPEL : l'extracteur AST de `test_i18n.py` ne
    voit pas ces clés et ne peut pas réclamer leur traduction."""

    def test_aucun_fait_ne_reste_en_francais(self):
        textes = set(tous_les_textes())
        for fichier in LANGUES:
            strings = json.loads(fichier.read_text(encoding="utf-8"))["strings"]
            manquants = sorted(textes - set(strings))
            assert not manquants, (
                f"{len(manquants)} fait(s) sans traduction dans "
                f"{fichier.name} : {manquants[:2]}")

    def test_aucune_traduction_ne_survit_a_son_fait(self):
        """Un fait reformulé laisse derrière lui une clé que plus personne
        n'affiche — et qu'un traducteur bénévole traduira pour rien."""
        textes = set(tous_les_textes())
        prefixes = ("Aujourd'hui, ", "Le 1", "Le 2", "Le 3")
        for fichier in LANGUES:
            strings = json.loads(fichier.read_text(encoding="utf-8"))["strings"]
            suspectes = [k for k in strings
                         if k.startswith(prefixes) and k not in textes]
            assert not suspectes, (fichier.name, suspectes[:3])


class TestLesDatesSontCoherentesAvecLesAmbiances:
    def test_la_date_de_la_bataille_tombe_dans_le_mois_de_la_bataille(self):
        assert current_season(date(2026, 5, 2)) == "bataille"

    def test_l_anniversaire_de_harry_tombe_dans_son_mois(self):
        assert current_season(date(2026, 7, 31)) == "anniversaire"

    def test_le_poudlard_express_tombe_dans_le_mois_de_la_rentree(self):
        assert current_season(date(2026, 9, 1)) == "rentree"

    def test_la_mort_des_potter_tombe_a_halloween(self):
        assert current_season(date(2026, 10, 31)) == "halloween"


class TestDansLaBarreDeStatut:
    """Là où « Prêt » vivait — un état NORMAL, que le projet s'interdit
    d'afficher partout ailleurs. Le fait du jour ne coûte donc aucun pixel, et
    tout message réel le remplace : c'est ce qui le rend non intrusif."""

    @staticmethod
    def _fenetre(qtbot, tmp_path, monkeypatch, faits=True):
        import pytest
        pytest.importorskip("pytestqt")
        import src.core.config as cfgmod
        from src.core.config import Config
        import src.ui.main_window as mw

        monkeypatch.setattr(cfgmod, "CONFIG_FILE_PATH", tmp_path / "config.json")
        Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache",
               langue="fr", autoplay_videos=False, faits_du_jour=faits).save()
        monkeypatch.setattr(mw.MainWindow, "_start_update_check", lambda self: None)
        w = mw.MainWindow()
        qtbot.addWidget(w)
        w._launcher_update_asked = True
        return w

    def test_le_fait_remplace_pret(self, qtbot, tmp_path, monkeypatch):
        w = self._fenetre(qtbot, tmp_path, monkeypatch, faits=True)
        assert w._message_au_repos() != "Prêt"
        assert w._message_au_repos()

    def test_desactive_on_retombe_sur_pret(self, qtbot, tmp_path, monkeypatch):
        w = self._fenetre(qtbot, tmp_path, monkeypatch, faits=False)
        assert w._message_au_repos() == "Prêt"

    def test_un_vrai_message_passe_devant(self, qtbot, tmp_path, monkeypatch):
        """Le fait occupe un SILENCE : dès qu'il y a quelque chose à dire, il
        s'efface. Sans ça, il faudrait choisir entre l'almanach et l'info."""
        w = self._fenetre(qtbot, tmp_path, monkeypatch, faits=True)
        w._on_update_counts(3)
        assert "3" in w._status_bar.currentMessage()
        w._online = False
        w._on_update_counts(0)
        assert "ligne" in w._status_bar.currentMessage()
        w._online = True
        w._on_update_counts(0)
        assert w._status_bar.currentMessage() == w._message_au_repos()
