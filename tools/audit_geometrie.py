"""Contrôle de mise en page AVEC LES VRAIES POLICES DE WINDOWS.

Pourquoi ce script existe alors qu'il y a déjà des tests de géométrie
=====================================================================
La suite de tests tourne sous `QT_QPA_PLATFORM=offscreen` (imposé par
`tests/conftest.py`, pour être exécutable sans écran et en CI). Or sous cette
plateforme `QFontDatabase.families()` renvoie **zéro famille** : ni Georgia —
la police de corps du launcher, `fonts.body_font()` — ni Segoe UI n'existent,
et Qt substitue silencieusement Cinzel, la seule police chargée par
l'application.

Mesuré : à corps égal, sur la même phrase, Cinzel est **22 % plus large** que
Georgia (421 px contre 344) et son interligne **16 % plus haut** (22 px contre
19). Autrement dit, tous les tests de troncature et de débordement de la suite
raisonnent sur une police que l'utilisateur ne verra jamais. Ils restent utiles
— Cinzel étant plus large, ils sont conservateurs sur la troncature — mais ils
ne peuvent pas trancher un empilement de hauteurs.

Ce script rejoue donc les mêmes contrôles sur la plateforme native, où les
polices sont réelles, avec `WA_DontShowOnScreen` : la fenêtre est construite,
mise en page et mesurable, mais elle n'apparaît jamais à l'écran. Il est appelé
par `build.bat` juste avant PyInstaller, c'est-à-dire sur la machine qui publie
— la seule qui ait à coup sûr les polices du poste cible.

Ce qu'il vérifie, pour 8 jeux × 4 états × 4 tailles × 2 scénarios × toutes
les langues :
  * aucun libellé tronqué horizontalement (sizeHint vs largeur accordée) ;
  * aucun libellé en `wordWrap` coupé en bas (heightForWidth vs hauteur) ;
  * aucune barre de défilement dans le panneau d'informations,
    fiche nominale ET fiche portant un avertissement de catalogue — c'est
    ce second cas qui manquait, et un débordement de 20 px en espagnol y
    a vécu sans être vu.

Usage :
    python tools/audit_geometrie.py            # toutes les langues
    python tools/audit_geometrie.py fr en      # seulement celles-ci
Sortie : code 0 si tout va bien, 1 sinon (et la liste des cas fautifs).
"""

import os
import sys
import tempfile
from collections import namedtuple
from pathlib import Path

# La plateforme native est le SUJET de ce script : on retire un éventuel
# forçage offscreen hérité de l'environnement appelant.
os.environ.pop("QT_QPA_PLATFORM", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TAILLES = [(980, 660), (1100, 720), (1320, 880), (1500, 950)]
SCENARIOS = ("nominal", "bandeau", "charge")

# Bloc de langue de test. Il ne vient PAS de games.json : le catalogue se met a
# jour a distance, et un controle qui suppose son contenu casse a chaque
# livraison de jeu. Trois langues, dont un libelle long, pour eprouver la ligne
# meta la ou elle risque de passer a la ligne.
_BLOC_LANGUE = {
    "root": "HKLM",
    "view": 32,
    "key": chr(92).join(["SOFTWARE", "Electronic Arts", "Jeu"]),
    "languages": {
        "fr": {"label": "Francais", "values": {"Language": "French"}},
        "en": {"label": "English", "values": {"Language": "English"}},
        "pt": {"label": "Portugues do Brasil", "values": {"Language": "Portuguese"}},
    },
}

# Avertissement de catalogue le plus long qu'on ait à publier, par langue. Il ne
# vient PAS de games.json : le catalogue se met à jour a distance, un controle
# qui suppose son contenu casserait a chaque livraison de jeu.
_AVERTISSEMENT = {
    "fr": ("Votre antivirus peut mettre en quarantaine un fichier de ce jeu pendant "
           "l'installation. S'il refuse de demarrer, restaurez ce fichier."),
    "en": ("Your antivirus may quarantine one of this game's files during installation. "
           "If the game will not start, restore that file."),
    "es": ("Su antivirus puede poner en cuarentena un archivo de este juego durante la "
           "instalacion. Si el juego no arranca, restaure ese archivo."),
}


def _mesure(langue: str, scenario: str = "nominal") -> list[str]:
    """Contrôle une langue. Retourne la liste des anomalies (vide si tout va bien).

    `scenario` choisit ce qui occupe la zone d'action :
      * "nominal"  — rien à signaler, la fiche dans son état ordinaire ;
      * "bandeau"  — un avertissement du catalogue sur TOUS les jeux, dans sa
        forme la plus longue (avec le lien « En savoir plus ») ;
      * "charge"   — le pire cas cumulé : cet avertissement PLUS le sélecteur de
        langue dans la ligne méta, avec un libellé volontairement long.

    Le second n'existait pas, et c'est ce qui a laissé passer un débordement de
    20 px en espagnol à 980×660 : la suite de tests mesure une police
    substituée, et ce script écartait le bandeau. Or le bandeau est justement
    ce qui mange le budget vertical du panneau.
    """
    tmp = Path(tempfile.mkdtemp(prefix="accio_geo_"))
    import src.core.config as cfgmod

    cfgmod.CONFIG_FILE_PATH = tmp / "config.json"
    from src.core.config import Config
    import src.core.game_manager as gm

    # Disque large : on teste la mise en page nominale, pas le bandeau d'alerte
    # (qui a ses propres tests et RACCOURCIT la description, donc masquerait le
    # cas le plus contraint).
    usage = namedtuple("usage", "total used free")
    gm.shutil.disk_usage = lambda _p: usage(0, 0, 900_000 * 1024 * 1024)

    vrai_load = getattr(gm.load_catalog, "__wrapped__", gm.load_catalog)
    if scenario == "nominal":
        gm.load_catalog = vrai_load
    else:
        import dataclasses

        from src.core.game_data import _parse_language_registry
        bloc = _parse_language_registry(_BLOC_LANGUE) if scenario == "charge" else None
        if scenario == "charge" and bloc is None:
            raise SystemExit("Le bloc de langue de test est refuse au parsing.")
        texte = _AVERTISSEMENT.get(langue, _AVERTISSEMENT["en"])

        def _charge(*a, **k):
            cat = vrai_load(*a, **k)
            jeux = []
            for g in cat.games:
                g = dataclasses.replace(
                    g, warning=texte,
                    warning_url="https://acciolauncher.be/aide/antivirus")
                if bloc is not None:
                    g = dataclasses.replace(g, language_registry=bloc)
                jeux.append(g)
            return dataclasses.replace(cat, games=tuple(jeux))

        _charge.__wrapped__ = vrai_load
        gm.load_catalog = _charge

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
    from src.core.game_manager import GameState
    from src.ui.main_window import MainWindow

    MainWindow._start_update_check = lambda self: None
    Config(install_path=tmp / "games", cache_path=tmp / "games" / ".cache",
           langue=langue, autoplay_videos=False).save()

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()

    def pompe(n: int = 12) -> None:
        for _ in range(n):
            app.processEvents()

    etats = [GameState.NOT_INSTALLED, GameState.INSTALLED,
             GameState.DOWNLOADING, GameState.INSTALLING]
    anomalies: list[str] = []
    vus: set[tuple[str, str]] = set()
    info = win._detail._info

    for taille in TAILLES:
        win.resize(*taille)
        pompe()
        for entry in win.manager.get_games():
            for etat in etats:
                win.manager.set_game_state(entry.game.id, etat)
                win._detail.set_game(entry.game)
                win._detail._refresh()
                pompe()
                ctx = "%s[%s] %dx%d %s %s" % (langue, scenario, taille[0],
                                              taille[1], entry.game.id, etat.name)
                reste = info._scroll.verticalScrollBar().maximum()
                if reste > 0:
                    anomalies.append(
                        "%s : le panneau d'infos defile (%d px de trop)" % (ctx, reste))
                for w in win.findChildren((QLabel, QPushButton)):
                    if not w.isVisible() or not w.text():
                        continue
                    texte = w.text()
                    if "<" in texte and ">" in texte:
                        continue  # richtext : mesure non pertinente
                    nom = w.objectName() or type(w).__name__
                    cle = (nom, texte[:40])
                    if isinstance(w, QLabel) and w.wordWrap():
                        besoin = w.heightForWidth(w.width())
                        if besoin > w.height() + 1 and cle not in vus:
                            vus.add(cle)
                            anomalies.append(
                                "%s : %s coupe en bas (%d px requis, %d accordes) — %r"
                                % (ctx, nom, besoin, w.height(), texte[:48]))
                        continue
                    besoin = w.sizeHint().width()
                    if besoin > w.width() + 1 and cle not in vus:
                        vus.add(cle)
                        anomalies.append(
                            "%s : %s tronque (%d px requis, %d accordes) — %r"
                            % (ctx, nom, besoin, w.width(), texte[:48]))
    win.close()
    return anomalies


def main() -> int:
    from PyQt6.QtGui import QFontDatabase
    from PyQt6.QtWidgets import QApplication

    app = QApplication([])
    familles = len(QFontDatabase.families())
    print("Plateforme Qt : %s — %d familles de polices"
          % (app.platformName(), familles))
    if familles == 0:
        print("ERREUR : aucune police systeme visible. Ce controle n'a de sens")
        print("         que sur la plateforme native (pas offscreen).")
        return 1

    from src.core.i18n import available_languages

    demandees = sys.argv[1:]
    codes = [info.code for info in available_languages()]
    if demandees:
        codes = [c for c in codes if c in demandees]
    print("Langues controlees : %s" % ", ".join(codes))
    print("Combinaisons par langue : %d jeux x 4 etats x %d tailles x %d scenarios"
          % (8, len(TAILLES), len(SCENARIOS)))
    print()

    total = 0
    for scenario in SCENARIOS:
        for code in codes:
            anomalies = _mesure(code, scenario)
            total += len(anomalies)
            etat = "OK" if not anomalies else "%d ANOMALIE(S)" % len(anomalies)
            print("  %-4s %-8s %s" % (code, scenario, etat))
            for a in anomalies[:12]:
                print("       - %s" % a)
            if len(anomalies) > 12:
                print("       - ... et %d autres" % (len(anomalies) - 12))

    print()
    if total:
        print("ECHEC : %d anomalie(s) de mise en page avec les vraies polices." % total)
        return 1
    print("Aucune troncature, aucun debordement, aucune barre de defilement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
