"""Pictogrammes des boutons : SVG Phosphor et logos officiels des marques.

Ils étaient d'abord des caractères posés dans des `QPushButton` — le
haut-parleur était U+1F50A, un EMOJI, que Windows rendait bleu au milieu d'une
interface or et blanche. Puis des tracés faits main, que Ludo a jugés trop
artisanaux (2026-09-19) : « je veux pas du fait maison je veux du vrai design ».
Ce sont désormais des SVG de `assets/icons/`, teintés au rendu.
"""

import hashlib
import pathlib

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter, QRegion  # noqa: E402
from PyQt6.QtSvg import QSvgRenderer  # noqa: E402
from PyQt6.QtWidgets import QWidget  # noqa: E402

from src.ui import icon_button, theme  # noqa: E402
from src.ui.icon_button import BLURPLE, ICONES, IconButton, pixmap_icone  # noqa: E402

_RACINE = pathlib.Path(__file__).resolve().parent.parent


def _peindre(bouton: IconButton) -> QImage:
    """Rend le bouton SEUL, sans le fond de fenêtre que `render` ajoute sinon."""
    img = QImage(bouton.width(), bouton.height(), QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    bouton.render(p, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)
    p.end()
    return img


def _pixels(img: QImage, alpha_min: int = 1) -> list[tuple[int, int, int, int]]:
    return [img.pixelColor(x, y).getRgb()
            for y in range(img.height()) for x in range(img.width())
            if img.pixelColor(x, y).alpha() >= alpha_min]


def _proche(c, cible, tolerance: int = 24) -> bool:
    return max(abs(c[i] - cible[i]) for i in range(3)) < tolerance


class TestLesFichiers:
    """Un fichier manquant ne lève rien : le bouton serait simplement VIDE."""

    @pytest.mark.parametrize("nom", ICONES)
    def test_chaque_icone_a_un_svg_lisible(self, qtbot, nom):
        chemin = icon_button._DOSSIER / icon_button._FICHIERS[nom]
        assert chemin.is_file(), chemin
        assert QSvgRenderer(str(chemin)).isValid(), chemin

    def test_le_logo_discord_du_survol_existe(self, qtbot):
        chemin = icon_button._DOSSIER / icon_button._DISCORD_SURVOL
        assert QSvgRenderer(str(chemin)).isValid(), chemin

    def test_la_licence_de_phosphor_voyage_avec_les_icones(self):
        """La MIT exige que sa mention accompagne toute copie : les SVG partent
        dans l'exe avec tout `assets/`, la licence doit partir avec eux."""
        licence = icon_button._DOSSIER / "phosphor" / "LICENSE.txt"
        assert "Phosphor Icons" in licence.read_text(encoding="utf-8")

    def test_les_provenances_sont_declarees(self):
        notices = (_RACINE / "docs" / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
        for nom in ("Phosphor", "Simple Icons", "Discord", "Ko-fi"):
            assert nom in notices, nom


class TestChaquePictogrammeSeDessine:
    """Un pictogramme qui ne peint rien ne se voit pas dans une suite offscreen."""

    @pytest.mark.parametrize("nom", ICONES)
    def test_il_y_a_de_l_encre(self, qtbot, nom):
        b = IconButton(nom)
        qtbot.addWidget(b)
        encre = _pixels(_peindre(b))
        assert len(encre) > 40, f"{nom} ne peint presque rien"

    @pytest.mark.parametrize("nom", ICONES)
    def test_l_encre_tient_dans_le_bouton(self, qtbot, nom):
        """Un pictogramme qui déborde serait rogné par le bouton voisin."""
        b = IconButton(nom)
        qtbot.addWidget(b)
        img = _peindre(b)
        bord = [(x, y) for y in (0, img.height() - 1) for x in range(img.width())]
        bord += [(x, y) for x in (0, img.width() - 1) for y in range(img.height())]
        debordements = [xy for xy in bord if img.pixelColor(*xy).alpha() > 40]
        assert not debordements, f"{nom} touche le bord du bouton"

    def test_deux_pictogrammes_different(self, qtbot):
        """Sinon `set_icone` pourrait ne rien changer sans qu'on le voie."""
        a, b = IconButton("play"), IconButton("pause")
        qtbot.addWidget(a)
        qtbot.addWidget(b)
        assert _peindre(a) != _peindre(b)

    def test_set_icone_repeint(self, qtbot):
        b = IconButton("volume")
        qtbot.addWidget(b)
        avant = _peindre(b)
        b.set_icone("muet")
        assert _peindre(b) != avant

    def test_une_icone_inconnue_est_refusee(self, qtbot):
        """Une faute de frappe doit tomber à la construction, pas au survol."""
        with pytest.raises(ValueError):
            IconButton("stop")


class TestLaTeinteNeDependPasDuFichier:
    """Un SVG Phosphor porte `currentColor`, celui de Ko-fi aucune couleur : la
    teinte est posée par-dessus le rendu, et doit valoir pour les deux."""

    @pytest.mark.parametrize("nom", ["reglages", "kofi", "play"])
    def test_toute_l_encre_prend_la_couleur_demandee(self, qtbot, nom):
        cible = (0x12, 0x9a, 0x56)
        encre = _pixels(pixmap_icone(nom, 40, QColor(*cible)).toImage(), alpha_min=96)
        assert encre, f"{nom} ne peint rien"
        ecarts = [c for c in encre if not _proche(c, cible, 10)]
        assert not ecarts, f"{nom} : {len(ecarts)} pixels hors teinte, ex. {ecarts[:3]}"

    def test_le_pixmap_rendu_est_une_copie(self, qtbot):
        """Le rendu est mis en cache : modifier ce qu'on reçoit ne doit pas
        repeindre en rouge le pictogramme du prochain appelant."""
        pm = pixmap_icone("site", 30)
        pm.fill(QColor("red"))
        assert not [c for c in _pixels(pixmap_icone("site", 30).toImage(), 96)
                    if _proche(c, (255, 0, 0))]


class TestLeSurvolPrendLaCouleurDeLaMaison:
    """Le pictogramme suit l'accent du thème — c'était impossible avec un emoji."""

    def test_le_trait_passe_a_l_accent(self, qtbot):
        b = IconButton("play")
        qtbot.addWidget(b)
        b._survol = True
        accent = theme.current().accent_rgb
        assert [c for c in _pixels(_peindre(b)) if _proche(c, accent)], (
            "aucun pixel à la couleur d'accent au survol")


class TestPlusAucunEmojiDansLaBarre:
    """Garde-fou de la règle maison : pas de pictogramme à présentation emoji.

    Elle est écrite dans CLAUDE.md depuis longtemps, et la barre audio la
    violait quand même — parce que rien ne la VÉRIFIAIT.
    """

    @pytest.mark.parametrize("fichier", ["src/ui/audio_bar.py",
                                         "src/ui/icon_button.py"])
    def test_aucun_caractere_du_plan_emoji(self, fichier):
        texte = (_RACINE / fichier).read_text(encoding="utf-8")
        fautifs = sorted({c for c in texte if ord(c) >= 0x1F000})
        assert not fautifs, f"pictogramme emoji dans {fichier} : {fautifs}"

    @pytest.mark.parametrize("fichier", ["src/ui/audio_bar.py",
                                         "src/ui/icon_button.py"])
    def test_aucune_echappee_du_plan_emoji(self, fichier):
        """L'échappée `\\U0001f50a` ne contient aucun caractère suspect : c'est
        du texte ASCII qui en produit un. C'est sous cette forme que le
        haut-parleur bleu vivait dans le fichier.

        Ce test cherchait jusqu'au 2026-09-19 la chaîne littérale
        `' + chr(92) + 'u0001f`, reste d'un script de génération : il ne
        pouvait rien trouver, et passait donc toujours."""
        texte = (_RACINE / fichier).read_text(encoding="utf-8").lower()
        assert "\\u0001f" not in texte


class TestDiscordResteLeLogoOfficiel:
    """Les règles de Discord : « ne pas modifier, déformer, recolorer ni
    reconfigurer le logo » ; seuls le blanc, le noir et le Blurple sont permis.

    Le Clyde tracé à la main avait demandé trois itérations et se lisait encore
    comme une tête d'ours. C'est désormais le fichier du kit officiel, et ces
    tests gardent ce qui casserait EN SILENCE : un fichier retouché, une teinte
    appliquée par erreur (or sur or au survol, donc Clyde sans visage), ou des
    proportions écrasées par un cadrage.

    **`qtbot` est demandé même quand aucun widget n'est créé** : `QPixmap` exige
    une `QApplication`, et sans elle Qt appelle `qFatal` — le processus est
    ABANDONNÉ (0xC0000409), sans trace ni sortie pytest. Invisible en jouant le
    fichier entier, fatal en jouant cette classe seule.
    """

    # Empreintes des fichiers du kit de marque de Discord, tels que téléchargés
    # depuis discord.com/branding le 2026-09-18. Aucun saut de ligne dedans :
    # `autocrlf` ne peut pas les modifier au checkout.
    _KIT = {
        "Discord-Symbol-White.svg":
            "de4cc484cdc0e3a8f3a58a84b0c80c5ac8acefeebf730930545ff3b279b5d0a3",
        "Discord-Symbol-Blurple.svg":
            "d06eaa51e78a9984ebbd3fbc82f0245ac2ecb5bf0150f537204397c1da5c7bd8",
    }

    @pytest.mark.parametrize("fichier", sorted(_KIT))
    def test_le_fichier_est_celui_du_kit_a_l_octet(self, fichier):
        donnees = (icon_button._DOSSIER / "marques" / fichier).read_bytes()
        assert hashlib.sha256(donnees).hexdigest() == self._KIT[fichier], (
            f"{fichier} a été modifié : Discord interdit de retoucher son logo")

    @staticmethod
    def _rendu(couleur: QColor, taille: int = 96) -> QImage:
        return pixmap_icone("discord", taille, couleur).toImage()

    @staticmethod
    def _boite(img: QImage) -> tuple[int, int, int, int]:
        pts = [(x, y) for y in range(img.height()) for x in range(img.width())
               if img.pixelColor(x, y).alpha() > 128]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    @pytest.mark.parametrize("couleur", [QColor("#ffffff"), BLURPLE])
    def test_les_yeux_sont_des_trous(self, qtbot, couleur):
        img = self._rendu(couleur)
        x0, y0, x1, y1 = self._boite(img)
        # Centres des yeux dans le tracé officiel (boîte 126,644 × 96).
        for fx in (42.28 / 126.644, 84.36 / 126.644):
            x, y = round(x0 + fx * (x1 - x0)), round(y0 + 52.76 / 96 * (y1 - y0))
            a = img.pixelColor(x, y).alpha()
            assert a == 0, f"oeil bouché en ({x}, {y}) : alpha={a}"

    @pytest.mark.parametrize("couleur", [QColor("#ffffff"), BLURPLE])
    def test_le_corps_est_plein(self, qtbot, couleur):
        """Le contrôle du test précédent : sans lui, un pictogramme entièrement
        vide passerait pour deux yeux parfaitement percés."""
        img = self._rendu(couleur)
        x0, y0, x1, y1 = self._boite(img)
        for fx, fy in ((0.5, 0.3), (0.5, 0.7), (0.15, 0.6), (0.85, 0.6)):
            x, y = round(x0 + fx * (x1 - x0)), round(y0 + fy * (y1 - y0))
            a = img.pixelColor(x, y).alpha()
            assert a > 200, f"corps troué en ({fx}, {fy}) : alpha={a}"

    def test_les_proportions_sont_celles_du_logo(self, qtbot):
        """126,644 × 96, soit 1,32 : un cadrage qui étirerait la boîte au carré
        déformerait la marque, ce que ses règles interdisent aussi."""
        x0, y0, x1, y1 = self._boite(self._rendu(QColor("#ffffff")))
        assert 1.25 < (x1 - x0) / (y1 - y0) < 1.40, f"{x1 - x0}x{y1 - y0}"

    def test_blanc_au_repos(self, qtbot):
        b = IconButton("discord", 36)
        qtbot.addWidget(b)
        encre = _pixels(_peindre(b), alpha_min=200)
        assert encre and all(_proche(c, (255, 255, 255), 4) for c in encre)

    def test_blurple_au_survol_jamais_l_or_de_la_maison(self, qtbot):
        b = IconButton("discord", 36)
        qtbot.addWidget(b)
        b._survol = True
        encre = _pixels(_peindre(b), alpha_min=200)
        assert [c for c in encre if _proche(c, BLURPLE.getRgb(), 6)], "pas de Blurple"
        accent = theme.current().accent_rgb
        assert not [c for c in encre if _proche(c, accent, 40)], "Discord teinté à l'or"

    def test_la_couleur_demandee_ne_teinte_pas_discord(self, qtbot):
        """`pixmap_icone("discord", couleur=or)` rend le logo BLANC : seuls le
        blanc et le Blurple sont permis, et un appelant distrait ne doit pas
        pouvoir en fabriquer un troisième."""
        encre = _pixels(self._rendu(QColor("#d6a72c")), alpha_min=200)
        assert encre and all(_proche(c, (255, 255, 255), 4) for c in encre)
