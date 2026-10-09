"""Page « À propos » des Paramètres : le colophon.

Refonte du 2026-10-09 (maquette validée par Ludo). L'ancienne page faisait se
suivre version, licence, mention légale et dépannage avec le même poids : rien
ne se lisait en premier, et le bouton de diagnostic avait l'air de l'action
principale. Ici, dans l'ordre : le logo et les numéros, trois tuiles (site,
Discord, Ko-fi), le générique, le dépannage en retrait, la mention légale.

Extraite de `settings_panel.py` le 2026-08-28. C'est la seule page du dialogue
qui ne règle RIEN : elle ne lit pas la config et n'en écrit pas.

Sa subtilité : le générique vient de DEUX sources (le catalogue distant et les
blocs `_meta.translators` des fichiers de langue), et les deux sont du texte
extérieur, jamais interprété.
"""

import logging
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import QMimeData, QPointF, QSize, QStandardPaths, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap, QPolygonF
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from src.core import diagnostic
from src.core.config import APP_VERSION, ASSETS_DIR, LOG_DIR
from src.core.i18n import tr, translator_credits
from src.core.liens import DEPOT_URL, DISCORD_URL, KOFI_URL, SITE_URL
from src.ui.composants import ENCRE, ENCRE_DISCRETE, ENCRE_DOUCE, police, texte
from src.ui.fonts import cinzel
from src.ui.icon_button import pixmap_icone
from src.ui.theme import accent_qcolor, current as current_theme, themed
from src.ui.utils import open_url

log = logging.getLogger(__name__)

_LOGO = ASSETS_DIR / "accio_logo_horizontal.png"
_LARGEUR_LOGO = 300
_LARGEUR_TUILE = 160
_TAILLE_ICONE = 24


def _capitales(contenu: str, px: int, encre: str, espacement: float = 2.0) -> QLabel:
    """Cinzel en capitales espacées : numéros, noms des tuiles, générique."""
    lbl = QLabel(contenu.upper())
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    f = cinzel(8, bold=True)
    f.setPixelSize(px)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, espacement)
    lbl.setFont(f)
    lbl.setStyleSheet(themed(f"color: {encre}; background: transparent;"))
    return lbl


def _logo() -> QLabel:
    lbl = QLabel()
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("background: transparent;")
    image = QPixmap(str(_LOGO))
    if image.isNull():
        lbl.setText("Accio Launcher")
        lbl.setFont(cinzel(20, bold=True))
        return lbl
    ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    image = image.scaledToWidth(round(_LARGEUR_LOGO * ratio),
                                Qt.TransformationMode.SmoothTransformation)
    image.setDevicePixelRatio(ratio)
    lbl.setPixmap(image)
    lbl.setAccessibleName("Accio Launcher")
    return lbl


class Tuile(QPushButton):
    """Un lien externe en carte : pictogramme, nom, et ce qu'on y trouve.

    Un vrai bouton, donc atteint au Tab et à la manette (règle 15). Le
    pictogramme est un SVG, jamais un glyphe : Ludo, 2026-08-26, « pour vite
    reconnaître sans lire ». Les libellés internes laissent passer la souris.
    """

    def __init__(self, nom: str, sous_titre: str, icone: str, url: str,
                 vedette: bool = False) -> None:
        super().__init__()
        self.nom = nom
        self.icone = icone
        self.setObjectName("tuileVedette" if vedette else "tuile")
        self.setAccessibleName(nom)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(_LARGEUR_TUILE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 14)
        lay.setSpacing(8)
        image = QLabel()
        image.setPixmap(pixmap_icone(
            icone, _TAILLE_ICONE, None if icone == "discord" else accent_qcolor(255)))
        lay.addWidget(image)
        lay.addWidget(_capitales(nom, 13, ENCRE, 1.5))
        legende = texte(sous_titre, 12, ENCRE_DOUCE, retour=True)
        lay.addWidget(legende)
        lay.addStretch()
        for enfant in self.findChildren(QLabel):
            enfant.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.clicked.connect(lambda: open_url(url))

    def sizeHint(self) -> QSize:
        # La légende passe à la ligne : sa hauteur dépend de la largeur fixe.
        lay = self.layout()
        hauteur = (lay.heightForWidth(_LARGEUR_TUILE) if lay.hasHeightForWidth()
                   else lay.sizeHint().height())
        return QSize(_LARGEUR_TUILE, hauteur)


_STYLE_TUILES = """
QPushButton#tuile, QPushButton#tuileVedette {
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.16);
    border-radius: 10px; text-align: left;
}
QPushButton#tuileVedette {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(214, 167, 44, 0.12), stop:1 rgba(214, 167, 44, 0.04));
    border-color: rgba(214, 167, 44, 0.40);
}
QPushButton#tuile:hover, QPushButton#tuileVedette:hover { border-color: #d6a72c; }
QPushButton#tuile[focusClavier="true"]:focus,
QPushButton#tuileVedette[focusClavier="true"]:focus { border: 2px solid #d6a72c; }
QFrame#depannage {
    border: 1px dashed rgba(255, 255, 255, 0.14); border-radius: 9px;
    background: transparent;
}
QPushButton#copierRapport {
    background: transparent; border: none; color: #d6a72c; padding: 4px 2px;
}
QPushButton#copierRapport:hover { color: #e8c547; }
QPushButton#copierRapport[focusClavier="true"]:focus { border-bottom: 2px solid #d6a72c; }
"""


def _tuiles() -> QHBoxLayout:
    domaine = urlparse(SITE_URL).netloc or SITE_URL
    # « Discord » et « Ko-fi » ne passent PAS par tr() : ce sont des noms
    # propres, identiques dans toutes les langues.
    kofi = Tuile("Ko-fi", tr("Offrir un café au projet"), "kofi", KOFI_URL, vedette=True)
    kofi.setToolTip(tr("Le launcher est gratuit — un café finance son développement et celui des correctifs."))
    tuiles = (Tuile(tr("Site web"), domaine, "site", SITE_URL),
              Tuile("Discord", tr("Questions, soucis et nouvelles du projet"),
                    "discord", DISCORD_URL),
              kofi)
    # Même hauteur pour les trois : la plus longue légende décide (elle passe
    # à la ligne selon la langue), sinon les cartes se décalent.
    hauteur = max(t.sizeHint().height() for t in tuiles)
    rangee = QHBoxLayout()
    rangee.setSpacing(14)
    rangee.addStretch()
    for tuile in tuiles:
        tuile.setFixedHeight(hauteur)
        rangee.addWidget(tuile, alignment=Qt.AlignmentFlag.AlignTop)
    rangee.addStretch()
    return rangee


class _Losange(QWidget):
    """Le petit losange entre un rôle et un nom. Peint : un ◆ dans le texte
    serait un pictogramme Unicode, rendu au hasard des polices (règle 59)."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(22, 12)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent_qcolor(120))
        cx, cy = self.width() / 2, self.height() / 2
        p.drawPolygon(QPolygonF([QPointF(cx, cy - 3.5), QPointF(cx + 3.5, cy),
                                 QPointF(cx, cy + 3.5), QPointF(cx - 3.5, cy)]))
        p.end()


def _filet() -> QFrame:
    trait = QFrame()
    trait.setFixedHeight(1)
    trait.setStyleSheet(themed("background: rgba(214, 167, 44, 0.25); border: none;"))
    return trait


def _nom_contributeur(c) -> QLabel:
    """Nom en RichText ÉCHAPPÉ : sans ça, le balisage d'un nom venu du
    catalogue serait INTERPRÉTÉ (mise en page détournée, `<img src="file:///…">`
    qui lit un fichier LOCAL). L'`url` a déjà été validée au parsing (https)."""
    nom = escape(c.name, quote=False)
    if c.url:
        nom = (f'<a href="{escape(c.url)}" style="color:{current_theme().accent};'
               f' text-decoration:none;">{nom}</a>')
    lbl = QLabel(nom)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse
                                | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
    lbl.linkActivated.connect(open_url)
    f = cinzel(8, bold=True)
    f.setPixelSize(13)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {ENCRE}; background: transparent;")
    return lbl


def _generique(contributeurs) -> QWidget | None:
    """Contributeurs du catalogue + traducteurs des fichiers de langue.

    DEUX sources, une seule rubrique. Les traducteurs s'ajoutent dans la même
    contribution que leur traduction ; les autres vivent dans le CATALOGUE, qui
    se met à jour à distance : remercier quelqu'un n'attend pas une release.
    Rien à afficher : pas de rubrique (un titre au-dessus de rien annoncerait
    une liste qui n'existe pas).
    """
    lignes: list[tuple[QLabel, QLabel]] = []
    for c in contributeurs:
        # Le rôle en PlainText : jamais interprété, sans rien à échapper.
        lignes.append((texte(c.role, 14, ENCRE_DOUCE), _nom_contributeur(c)))
    for langue, gens in translator_credits():
        # PlainText aussi : un fichier de langue vient de l'extérieur.
        nom = _capitales(", ".join(gens), 13, ENCRE, 1.5)
        nom.setText(", ".join(gens))
        lignes.append((texte(f"{tr('Traductions')} · {langue}", 14, ENCRE_DOUCE), nom))
    if not lignes:
        return None

    bloc = QWidget()
    lay = QVBoxLayout(bloc)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    titre = QHBoxLayout()
    titre.setSpacing(14)
    titre.addWidget(_filet(), stretch=1)
    titre.addWidget(_capitales(tr("Générique"), 11, "#d6a72c", 4))
    titre.addWidget(_filet(), stretch=1)
    lay.addLayout(titre)
    grille = QGridLayout()
    grille.setHorizontalSpacing(0)
    grille.setVerticalSpacing(8)
    grille.setColumnStretch(0, 1)
    grille.setColumnStretch(2, 1)
    for rang, (role, nom) in enumerate(lignes):
        role.setFont(police(14))
        f = role.font()
        f.setItalic(True)
        role.setFont(f)
        role.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        role.setWordWrap(True)
        nom.setWordWrap(True)
        grille.addWidget(role, rang, 0)
        grille.addWidget(_Losange(), rang, 1, Qt.AlignmentFlag.AlignVCenter)
        grille.addWidget(nom, rang, 2)
    lay.addLayout(grille)
    return bloc


def _mention_legale() -> QLabel:
    """Copyright, licence et lien vers le code source.

    La GPL v3 appelle ces « mentions légales appropriées » ; les termes
    additionnels (ADDITIONAL-TERMS.md, article 7 b) exigent qu'une version
    dérivée les CONSERVE dans son « À propos ». Encore faut-il que l'original
    les affiche. Le lien mène au dépôt, qui porte le code ET la licence.
    """
    lien = (f'<a href="{escape(DEPOT_URL)}" style="color:{current_theme().accent}; '
            f'text-decoration:none;">{escape(tr("Code source et licence"), quote=False)}</a>')
    lbl = QLabel(escape(tr(
        "© 2026 ASTeam · logiciel libre sous licence GNU GPL v3, "
        "fourni sans aucune garantie"), quote=False) + " · " + lien
        + "<br>" + escape(tr(
            "Les jeux restent la propriété de Warner Bros. et d'Electronic Arts : "
            "pour y jouer légalement, il faut en posséder une copie originale "
            "(CD, DVD ou achat numérique)."), quote=False))
    lbl.setObjectName("mentionLegale")
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setWordWrap(True)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFont(police(12))
    lbl.setStyleSheet(f"color: {ENCRE_DISCRETE}; background: transparent;")
    lbl.setTextInteractionFlags(
        Qt.TextInteractionFlag.LinksAccessibleByMouse
        | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
    )
    lbl.linkActivated.connect(open_url)
    return lbl


# Durée pendant laquelle le bouton confirme la copie avant de reprendre son
# libellé. Assez longue pour être lue, assez courte pour ne pas faire croire
# que la copie est un état.
_CONFIRMATION_MS = 4000


def texte_diagnostic(manager) -> str:
    """Le bloc de diagnostic complet : écrans et journal lus ici, le reste en core."""
    ecrans = [diagnostic.ecran(e.size().width(), e.size().height(), e.devicePixelRatio())
              for e in QGuiApplication.screens()]
    try:
        journal = (LOG_DIR / "accio_launcher.log").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        journal = ""
    return diagnostic.rapport(manager, ecrans=ecrans, journal=journal)


# Nom FIXE : chaque copie remplace la précédente, rien ne s'accumule.
NOM_RAPPORT = "Accio Launcher - rapport.txt"


def dossier_du_rapport() -> Path:
    """Le Bureau : c'est là qu'on retrouve un fichier qu'on n'a pas cherché."""
    bureau = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    return Path(bureau) if bureau and Path(bureau).is_dir() else LOG_DIR


def enregistrer_rapport(manager, resume: str) -> Path | None:
    """Écrit le rapport complet (résumé + tous les journaux) ; None si impossible."""
    journaux = [("launcher · " + f.name, f) for f in sorted(LOG_DIR.glob("*.log"))]
    journaux += diagnostic.journaux_des_jeux(manager)
    texte_complet = diagnostic.rapport_complet(
        resume, [(nom, diagnostic.lire_la_fin(f)) for nom, f in journaux])
    chemin = dossier_du_rapport() / NOM_RAPPORT
    try:
        chemin.write_text(texte_complet, encoding="utf-8")
    except OSError as exc:
        log.warning("Rapport complet non écrit (%s) : %s", chemin, exc)
        return None
    return chemin


def presse_papiers(resume: str, fichier: Path | None) -> QMimeData:
    """Le FICHIER (Ctrl+V sur Discord le joint) et le résumé en texte, pour
    tout endroit qui n'accepte pas de fichier."""
    donnees = QMimeData()
    if fichier is not None:
        donnees.setUrls([QUrl.fromLocalFile(str(fichier))])
    donnees.setText(resume)
    return donnees


def _bouton_diagnostic(manager) -> QPushButton:
    """« Copier le rapport » : la réponse à la première question de tout
    dépannage sur le Discord (version, Windows, jeux, erreurs), sans rien avoir
    à dicter. Rien n'est envoyé : c'est le presse-papiers, et la personne voit
    ce qu'elle colle.
    """
    libelle = tr("Copier le rapport")
    btn = QPushButton(libelle)
    btn.setObjectName("copierRapport")
    btn.setFont(police(13, gras=True))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    # La confirmation est plus longue que le libellé : le bouton ne doit pas
    # changer de largeur sous le curseur.
    confirmation = tr("Copié. Ctrl+V sur le Discord joint le rapport.")
    fm = btn.fontMetrics()
    btn.setMinimumWidth(max(fm.horizontalAdvance(libelle),
                            fm.horizontalAdvance(confirmation)) + 12)

    # Minuteur POSSÉDÉ par le bouton : il meurt avec lui (fermer les Paramètres
    # pendant la confirmation ne laisse rien viser un widget détruit), et un
    # second clic remet le délai à zéro au lieu d'en armer un deuxième.
    retour = QTimer(btn)
    retour.setSingleShot(True)
    retour.setInterval(_CONFIRMATION_MS)
    retour.timeout.connect(lambda: btn.setText(libelle))

    def copier():
        resume = texte_diagnostic(manager)
        QGuiApplication.clipboard().setMimeData(
            presse_papiers(resume, enregistrer_rapport(manager, resume)))
        btn.setText(confirmation)
        retour.start()

    btn.clicked.connect(copier)
    return btn


def _depannage(manager) -> QFrame:
    cadre = QFrame()
    cadre.setObjectName("depannage")
    lay = QHBoxLayout(cadre)
    lay.setContentsMargins(16, 10, 16, 10)
    lay.setSpacing(14)
    image = QLabel()
    image.setPixmap(pixmap_icone("rapport", 18, QColor("#a9a7c4")))
    image.setStyleSheet("background: transparent;")
    lay.addWidget(image, alignment=Qt.AlignmentFlag.AlignVCenter)
    phrase = texte(tr(
        "Un souci ? Copiez le rapport de dépannage, une copie va aussi sur votre "
        "Bureau, et collez-le sur le Discord. Il est anonymisé."), 13, "#a9a7c4", retour=True)
    phrase.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    lay.addWidget(phrase, stretch=1)
    lay.addWidget(_bouton_diagnostic(manager), alignment=Qt.AlignmentFlag.AlignVCenter)
    return cadre


def construire(contributeurs, manager=None) -> QWidget:
    """La page complète, prête à entrer dans le QStackedWidget des Paramètres."""
    page = QWidget()
    page.setStyleSheet(themed(_STYLE_TUILES))
    lay = QVBoxLayout(page)
    lay.setContentsMargins(0, 4, 0, 0)
    lay.setSpacing(0)

    lay.addWidget(_logo())
    lay.addSpacing(10)
    numeros = tr("Version {}").format(APP_VERSION)
    if manager is not None:
        numeros += "  ·  " + tr("Catalogue {}").format(manager.catalog.catalog_version)
    version = _capitales(numeros, 12, "#a9a7c4", 3)
    version.setObjectName("versions")
    version.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(version)
    lay.addSpacing(14)
    devise = texte(tr("Les jeux Harry Potter sur PC, réunis et prêts à jouer."), 16, "#c4c2da")
    f = devise.font()
    f.setItalic(True)
    devise.setFont(f)
    devise.setAlignment(Qt.AlignmentFlag.AlignCenter)
    devise.setWordWrap(True)
    lay.addWidget(devise)
    lay.addSpacing(26)
    lay.addLayout(_tuiles())

    generique = _generique(contributeurs)
    if generique is not None:
        lay.addSpacing(26)
        lay.addWidget(generique)
    if manager is not None:
        lay.addSpacing(22)
        lay.addWidget(_depannage(manager))
    lay.addStretch()
    lay.addSpacing(18)
    lay.addWidget(_mention_legale())
    return page
