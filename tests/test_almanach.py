"""L'Almanach de Poudlard — les dates, et les profils qui les habillent.

Le calendrier et les profils sont des DONNÉES PURES (`src/core/season.py`), donc
tout ce fichier tourne sans `QApplication` sauf la dernière classe, qui vérifie
que le rendu sait peindre ce que les données décrivent.

Ce que ces tests gardent vraiment : qu'ajouter un jour à l'Almanach reste une
ligne de table. Avant, les nombres d'une ambiance vivaient dans une cascade de
`if season == …` au milieu du constructeur d'une particule — invérifiable sans
construire un widget, et illisible au-delà de deux ambiances.
"""

from dataclasses import fields
from datetime import date

import pytest

from src.core.season import (
    PROFILS, SEASON_LABELS, SEASONS, Profil, current_season, profil, resolve,
)


class TestLeCalendrier:
    """Un MOIS, une ambiance.

    La première version limitait l'anniversaire et la bataille à leur jour
    exact, et la rentrée à une semaine. Ludo a tranché le 2026-09-23 : le mois
    entier. Il a raison sur le fond — une ambiance qu'on ne voit qu'un jour par
    an n'existe pas pour la plupart des gens, et celui qui la manque n'a aucun
    moyen de savoir qu'elle a existé. Le JOUR reste ce qui compte pour le fait
    du jour, qui change tous les jours ; l'ambiance habille la saison.
    """

    def test_septembre_entier_est_la_rentree(self):
        for jour in (1, 15, 30):
            assert current_season(date(2026, 9, jour)) == "rentree", jour

    def test_juillet_entier_est_l_anniversaire(self):
        for jour in (1, 17, 31):
            assert current_season(date(2026, 7, jour)) == "anniversaire", jour

    def test_mai_entier_est_la_bataille(self):
        for jour in (1, 2, 31):
            assert current_season(date(2026, 5, jour)) == "bataille", jour

    def test_octobre_est_halloween(self):
        for jour in (1, 15, 31):
            assert current_season(date(2026, 10, jour)) == "halloween", jour

    def test_decembre_est_noel_et_deborde_sur_janvier(self):
        """Le launcher reste en tenue de fête pendant les vacances, pas
        seulement en décembre."""
        assert current_season(date(2026, 12, 1)) == "noel"
        assert current_season(date(2026, 12, 25)) == "noel"
        assert current_season(date(2027, 1, 6)) == "noel"
        assert current_season(date(2027, 1, 7)) == "aucune"

    def test_les_mois_sans_ambiance_rendent_aucune(self):
        """Sept mois sur douze restent ordinaires, et c'est voulu : une
        ambiance permanente n'est plus une ambiance."""
        for mois in (2, 3, 4, 6, 8, 11):
            assert current_season(date(2026, mois, 15)) == "aucune", mois
        assert current_season(date(2026, 1, 20)) == "aucune"

    def test_chaque_mois_ne_rend_qu_une_ambiance(self):
        """Balayage des 365 jours : aucune date ne doit tomber dans un trou
        ni rendre une ambiance inconnue."""
        from datetime import timedelta
        jour = date(2026, 1, 1)
        vus = set()
        while jour.year == 2026:
            saison = current_season(jour)
            assert saison in SEASONS, (jour, saison)
            vus.add(saison)
            jour += timedelta(days=1)
        assert vus == {"aucune", "bataille", "anniversaire", "rentree",
                       "halloween", "noel"}

class TestResolve:
    def test_auto_suit_la_date(self):
        assert resolve("auto", date(2026, 9, 1)) == "rentree"
        assert resolve("auto", date(2026, 6, 11)) == "aucune"

    def test_le_choix_manuel_gagne(self):
        """C'est tout l'intérêt du menu : essayer le 1ᵉʳ septembre en juin."""
        assert resolve("rentree", date(2026, 6, 11)) == "rentree"
        assert resolve("aucune", date(2026, 12, 25)) == "aucune"

    def test_une_valeur_inconnue_retombe_sur_aucune(self):
        assert resolve("citrouille", date(2026, 10, 1)) == "aucune"


class TestLaTableTientDebout:
    """Les incohérences qu'une table de données rend possibles."""

    def test_chaque_ambiance_a_son_profil(self):
        manquants = [s for s in SEASONS if s != "auto" and s not in PROFILS]
        assert not manquants, (
            f"ambiance sans profil : {manquants} — elle s'afficherait dans les "
            "Paramètres et ne changerait rien à l'écran")

    def test_chaque_ambiance_a_son_libelle(self):
        assert set(SEASON_LABELS) == set(SEASONS), (
            "un libellé manquant ferait planter le sélecteur des Paramètres, "
            "un libellé en trop est une ambiance qu'on a oublié de retirer")

    def test_un_profil_inconnu_retombe_sur_l_ordinaire(self):
        """Une `config.json` écrite par une version plus récente peut nommer
        une ambiance que ce launcher n'a pas."""
        assert profil("ambiance_du_futur") == PROFILS["aucune"]

    def test_les_palettes_sont_completes(self):
        """Les parts doivent couvrir 1 : un cumul à 0,9 laisserait 10 % des
        tirages tomber dans le repli de fin de boucle, donc une couleur qui
        n'a pas été choisie."""
        for nom, p in PROFILS.items():
            total = sum(part for _, part in p.palette)
            assert abs(total - 1.0) < 1e-6, f"{nom} : palette à {total}"

    def test_aucune_ambiance_n_est_la_copie_d_une_autre(self):
        """Une ambiance ajoutée par copier-coller et jamais retouchée est un
        libellé de plus dans le menu pour exactement le même écran."""
        vus: dict[tuple, str] = {}
        for nom, p in PROFILS.items():
            empreinte = tuple(
                tuple(getattr(p, f.name)) if isinstance(getattr(p, f.name), (tuple, list))
                else getattr(p, f.name)
                for f in fields(Profil))
            assert empreinte not in vus, f"{nom} est identique à {vus[empreinte]}"
            vus[empreinte] = nom

    def test_une_forme_partielle_declare_sa_taille_de_fond(self):
        """`part_forme < 1` veut dire « le reste fait le fond » ; sans
        `taille_fond`, cette poudreuse sortirait à la taille des flocons."""
        for nom, p in PROFILS.items():
            if p.part_forme < 1.0:
                assert p.taille_fond is not None, nom

    def test_les_intervalles_vont_du_petit_au_grand(self):
        for nom, p in PROFILS.items():
            for champ in ("taille", "vitesse_y", "derive_x", "scintillement",
                          "opacite", "variation", "halo", "vitesse_rotation",
                          "taille_fond"):
                bornes = getattr(p, champ)
                if bornes is None:
                    continue
                assert bornes[0] <= bornes[1], f"{nom}.{champ} = {bornes}"


class TestLeRenduSaitPeindreCeQueLaTableDecrit:
    """La seule classe qui a besoin de Qt."""

    def test_chaque_forme_declaree_est_peignable(self, qtbot):
        from src.ui.particles import _FORMES
        for nom, p in PROFILS.items():
            assert p.forme == "point" or p.forme in _FORMES, (
                f"{nom} déclare la forme « {p.forme} », que personne ne sait "
                "dessiner — elle sortirait en point sans le dire")

    def test_les_particules_respectent_le_profil(self, qtbot):
        from src.ui.particles import ParticleOverlay
        overlay = ParticleOverlay()
        qtbot.addWidget(overlay)
        overlay.resize(400, 300)
        for nom, attendu in PROFILS.items():
            overlay.apply_season(nom)
            overlay._ensure_particles()
            assert len(overlay._particles) == attendu.nombre, nom
            for pt in overlay._particles:
                assert pt.shape in ("point", attendu.forme), nom
                assert attendu.vitesse_y[0] <= pt.speed_y <= attendu.vitesse_y[1], nom
        overlay.pause()

    def test_la_zone_sale_couvre_la_forme_entiere(self, qtbot):
        """Une enveloppe déborde de son rayon `size` : si la zone repeinte ne
        la couvre pas, elle laisse une trainée à l'écran."""
        from src.ui.particles import ParticleOverlay, _ETALEMENT
        overlay = ParticleOverlay()
        qtbot.addWidget(overlay)
        overlay.resize(400, 300)
        overlay.apply_season("rentree")
        overlay._ensure_particles()
        for pt in overlay._particles:
            zone = overlay._zone(pt)
            etendue = pt.size * _ETALEMENT.get(pt.shape, 1.0)
            assert zone.width() >= 2 * etendue
            assert zone.contains(int(pt.x), int(pt.y))
        overlay.pause()

    @pytest.mark.parametrize("ambiance", [s for s in SEASONS if s != "auto"])
    def test_chaque_ambiance_se_peint_sans_erreur(self, qtbot, ambiance):
        """Peindre pour de vrai : un `QPainterPath` mal formé ou une couleur
        absente ne se voit pas à la lecture du profil."""
        from PyQt6.QtGui import QImage, QPainter, QRegion
        from PyQt6.QtCore import QPoint
        from PyQt6.QtWidgets import QWidget
        from src.ui.particles import ParticleOverlay

        overlay = ParticleOverlay()
        qtbot.addWidget(overlay)
        overlay.resize(200, 150)
        overlay.apply_season(ambiance)
        overlay._ensure_particles()
        image = QImage(200, 150, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        peintre = QPainter(image)
        overlay.render(peintre, QPoint(), QRegion(overlay.rect()),
                       QWidget.RenderFlag.DrawChildren)
        peintre.end()
        overlay.pause()
        # Quelque chose a été peint : une ambiance qui ne dessine rien est un
        # menu qui ment.
        assert any(image.pixelColor(x, y).alpha() > 0
                   for x in range(0, 200, 3) for y in range(0, 150, 3)), ambiance
