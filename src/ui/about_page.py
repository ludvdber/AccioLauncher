"""Page « À propos » des Paramètres — version, liens, remerciements.

Extraite de `settings_panel.py` le 2026-08-28. C'est la seule des cinq pages du
dialogue qui ne règle RIEN : elle ne lit pas la config, n'en écrit pas, n'émet
aucun signal de changement et ne participe à aucun des va-et-vient
« modifier → sauver → redémarrer » qui occupent le reste du fichier. Elle y
vivait par voisinage, pas par parenté.

Elle a en revanche sa propre subtilité, qui se perdait au milieu des combos :
les remerciements viennent de DEUX sources (le catalogue distant et les blocs
`_meta.translators` des fichiers de langue) et l'une d'elles est du texte
extérieur qu'il faut échapper.
"""

from html import escape

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from src.core import diagnostic
from src.core.config import APP_VERSION, LOG_DIR
from src.core.i18n import tr, translator_credits
from src.core.liens import DISCORD_URL, KOFI_URL, SITE_URL
from src.ui.icon_button import pixmap_icone
from src.ui.theme import current as current_theme
from src.ui.utils import open_url


def _section(texte: str) -> QLabel:
    lbl = QLabel(texte)
    lbl.setObjectName("sectionTitle")
    return lbl


def _sous_titre(texte: str) -> QLabel:
    lbl = QLabel(texte)
    lbl.setObjectName("subtitle")
    lbl.setWordWrap(True)
    return lbl


# Sous ~1,5 px, un trait ne peut plus occuper une colonne entière : il s'étale
# sur deux, à alpha partiel, et le pictogramme devient de la brume. **Mesuré
# le 2026-08-30 à 16 px : 59 % de l'encre du globe et 61 % de celle de la tasse
# étaient de l'antialiasing**, pas du trait. À 22 px, le trait des SVG Phosphor
# Bold (3/32 de la boîte) mesure 2 px, et 2,6 px physiques à 125 %.
_TAILLE_ICONE = 22

# `QPushButton` colle le libellé au pictogramme : il n'expose aucun réglage
# d'écartement, et une feuille de style ne sait pas viser l'icône (`::icon`
# n'existe pas). Sur la capture de Ludo le « K » de Ko-fi touchait l'anse de la
# tasse et le « S » de Site web le globe — d'autant plus visible une fois les
# pictogrammes agrandis. Le blanc est donc peint DANS le pixmap : ça reste
# local au bouton, ça ne touche ni les libellés ni les traductions (des espaces
# en tête de chaîne seraient traduits, donc perdus au premier contributeur).
_ECART_ICONE = 8


def _icone_espacee(icone: str, encre: str) -> QIcon:
    """Le pictogramme suivi d'un blanc, en un seul pixmap.

    Le `devicePixelRatio` est repris tel quel : le recalculer ici le ferait
    diverger de `pixmap_icone`, et sur l'écran de Ludo (125 %) un pixmap à
    l'échelle 1 remonterait flou — exactement ce que cette passe corrige.
    """
    pm = pixmap_icone(icone, _TAILLE_ICONE, QColor(encre))
    ratio = pm.devicePixelRatio()
    large = QPixmap(round((_TAILLE_ICONE + _ECART_ICONE) * ratio),
                    round(_TAILLE_ICONE * ratio))
    large.setDevicePixelRatio(ratio)
    large.fill(Qt.GlobalColor.transparent)
    p = QPainter(large)
    p.drawPixmap(0, 0, pm)
    p.end()
    return QIcon(large)


def _bouton_lien(libelle: str, icone: str, url: str,
                 objet: str = "btnPath", encre: str = "#ffffff") -> QPushButton:
    """Bouton « pictogramme + libellé » vers un lien externe.

    Le pictogramme est un SVG (`pixmap_icone`), jamais un glyphe : Ludo,
    2026-08-26 — « il y a pas de logo web ou discord dans le à propos donc c'est
    pas fou pour vite reconnaître sans lire ». Trois libellés de longueurs
    voisines dans un cadre gris se ressemblent tous ; le Clyde et la tasse
    OFFICIELS, et un globe, se distinguent avant d'être lus — et survivent à la
    traduction, ce qu'un libellé ne fait pas.
    """
    btn = QPushButton(libelle)
    btn.setObjectName(objet)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setIcon(_icone_espacee(icone, encre))
    btn.setIconSize(QSize(_TAILLE_ICONE + _ECART_ICONE, _TAILLE_ICONE))
    btn.clicked.connect(lambda: open_url(url))
    return btn


def _credits_traducteurs() -> str:
    """Remerciements aux traducteurs, une ligne par langue.

    Alimenté par le bloc `_meta.translators` de chaque fichier de langue : un
    contributeur s'ajoute dans la même PR que sa traduction, sans qu'on ait à
    toucher au code.
    """
    credits = translator_credits()
    if not credits:
        return ""
    lignes = [tr("Traductions")]
    lignes += [f"{nom} — {', '.join(gens)}" for nom, gens in credits]
    return "\n".join(lignes)


def _remerciements(contributeurs) -> list[QWidget]:
    """Contributeurs du catalogue + traducteurs des fichiers de langue.

    DEUX sources, une seule rubrique à l'écran. Les traducteurs vivent dans le
    bloc `_meta.translators` de leur propre fichier de langue — ils s'ajoutent
    dans la même contribution que la traduction, ce qui est le bon endroit.
    Tous les autres vivent dans le CATALOGUE, qui se met à jour à distance :
    remercier quelqu'un ne doit pas attendre une release, sinon la personne voit
    passer trois versions sans son nom et n'en propose pas une deuxième.
    """
    traducteurs = _credits_traducteurs()
    if not contributeurs and not traducteurs:
        return []

    widgets: list[QWidget] = [_section(tr("Remerciements"))]
    if contributeurs:
        lignes = []
        for c in contributeurs:
            # RichText : tout ce qui vient du catalogue est ÉCHAPPÉ. Sans ça,
            # le balisage d'un nom de contributeur serait INTERPRÉTÉ — mise en
            # page détournée, et un `<img src="file:///…">` qui lit un fichier
            # LOCAL. L'`url`, elle, a déjà été validée au parsing (https seul).
            nom = escape(c.name, quote=False)
            if c.url:
                nom = (f'<a href="{escape(c.url)}" style="color:'
                       f'{current_theme().accent}; text-decoration:none;">{nom}</a>')
            lignes.append(f"{nom} — {escape(c.role, quote=False)}" if c.role else nom)
        lbl = QLabel("<br>".join(lignes))
        lbl.setObjectName("subtitle")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        lbl.linkActivated.connect(open_url)
        widgets.append(lbl)

    if traducteurs:
        lbl = QLabel(traducteurs)
        lbl.setObjectName("subtitle")
        # PlainText : ce texte vient d'un fichier de langue déposé par un
        # contributeur, donc de l'extérieur lui aussi.
        lbl.setTextFormat(Qt.TextFormat.PlainText)
        lbl.setWordWrap(True)
        widgets.append(lbl)
    return widgets


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


def _bouton_diagnostic(manager) -> QPushButton:
    """« Copier les informations de diagnostic » — la réponse à la première
    question de tout dépannage sur le Discord (version, Windows, jeux, erreurs),
    sans rien avoir à dicter. Rien n'est envoyé : c'est le presse-papiers, et
    la personne voit ce qu'elle colle.
    """
    libelle = tr("Copier les informations de diagnostic")
    btn = QPushButton(libelle)
    btn.setObjectName("btnPath")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    # La confirmation est plus longue que le libellé : le bouton ne doit pas
    # changer de largeur sous le curseur.
    confirmation = tr("Copié — collez-le sur le Discord")
    fm = btn.fontMetrics()
    btn.setMinimumWidth(max(fm.horizontalAdvance(libelle),
                            fm.horizontalAdvance(confirmation)) + 40)

    # Minuteur POSSÉDÉ par le bouton : il meurt avec lui (fermer les Paramètres
    # pendant la confirmation ne laisse rien viser un widget détruit), et un
    # second clic remet le délai à zéro au lieu d'en armer un deuxième.
    retour = QTimer(btn)
    retour.setSingleShot(True)
    retour.setInterval(_CONFIRMATION_MS)
    retour.timeout.connect(lambda: btn.setText(libelle))

    def copier():
        QGuiApplication.clipboard().setText(texte_diagnostic(manager))
        btn.setText(confirmation)
        retour.start()

    btn.clicked.connect(copier)
    return btn


def construire(contributeurs, manager=None) -> QWidget:
    """La page complète, prête à entrer dans le QStackedWidget des Paramètres."""
    rangee = QHBoxLayout()
    rangee.setSpacing(10)
    rangee.addWidget(_bouton_lien(tr("Site web"), "site", SITE_URL))
    # « Discord » et « Ko-fi » ne passent PAS par tr() : ce sont des noms
    # propres, identiques dans toutes les langues. Les y faire passer obligeait
    # à écrire trois traductions identiques, ce que la suite refuse à juste
    # titre (`test_pas_de_traduction_identique`).
    rangee.addWidget(_bouton_lien("Discord", "discord", DISCORD_URL))
    # Le ❤ du libellé disparaît : la tasse dit déjà « café », et deux symboles
    # pour un seul bouton, c'est un de trop. Les libellés raccourcissent aussi —
    # « Rejoindre le Discord » et « Soutenir sur Ko-fi » débordaient de leur
    # cadre une fois l'icône posée devant, et c'est précisément ce qu'un
    # pictogramme reconnaissable permet d'économiser : le nom suffit quand la
    # forme a déjà dit quoi.
    kofi = _bouton_lien("Ko-fi", "kofi", KOFI_URL, objet="btnKofi", encre="#e8c547")
    kofi.setToolTip(tr("Le projet est gratuit — un café aide à payer l'hébergement !"))
    rangee.addWidget(kofi)
    rangee.addStretch()

    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lay.addWidget(_section(tr("À propos")))
    lay.addWidget(_sous_titre(tr("Launcher pour les jeux Harry Potter sur PC.")))
    version = QLabel(f"Accio Launcher v{APP_VERSION}")
    version.setObjectName("subtitle")
    lay.addWidget(version)
    lay.addLayout(rangee)
    if manager is not None:
        lay.addWidget(_sous_titre(tr(
            "Un souci ? Ces informations aident à vous dépanner sur le Discord : "
            "version, Windows, jeux installés, dernières erreurs. Rien de personnel.")))
        ligne = QHBoxLayout()
        ligne.addWidget(_bouton_diagnostic(manager))
        ligne.addStretch()
        lay.addLayout(ligne)
    for w in _remerciements(contributeurs):
        lay.addWidget(w)
    lay.addStretch()
    return page
