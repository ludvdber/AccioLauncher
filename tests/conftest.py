"""Configuration pytest globale.

Force le platform Qt à offscreen pour les CI sans display, et fournit
des fixtures réutilisables pour les tests UI.
"""

import gc
import os

# Doit être posé AVANT tout import PyQt6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# Charger les modules d'extension Qt MAINTENANT, à la collecte, alors qu'il
# n'existe encore aucun objet Qt ni QApplication.
#
# `QtNetwork` n'était importé que tardivement, à l'intérieur d'un test ou d'un
# fixture. Créer un module d'extension C au milieu d'une session — donc pendant
# que le ramasse-miettes peut passer sur des objets Qt vivants — a provoqué un
# « Windows fatal exception: access violation » pendant un build, dans
# `enum.py` au moment de la création du module. Le plantage est ALÉATOIRE :
# il dépend du moment où le GC se déclenche, et il fait échouer un build au
# hasard. Importer tôt supprime la fenêtre de tir.
from PyQt6 import QtNetwork  # noqa: F401,E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _config_hors_du_vrai_dossier(tmp_path, monkeypatch):
    """Aucun test n'écrit dans le config.json RÉEL de l'utilisateur.

    `Config.save()` vise `src.core.config.CONFIG_FILE_PATH`. Un test — ou un
    script de mise au point — qui construit une Config et la sauve avant d'avoir
    redirigé ce chemin écrase le fichier réel : dossier d'installation, versions
    installées, temps de jeu. C'est arrivé le 2026-08-18 et les statistiques de
    jeu ont été perdues. Cette garde rend l'accident impossible depuis les tests.
    """
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH",
                        tmp_path / "config_test.json")
    yield


@pytest.fixture(autouse=True)
def _sauvegardes_hors_du_vrai_disque(tmp_path, monkeypatch):
    """Aucun test ne lit les VRAIES sauvegardes de la machine.

    `sauvegardes.racines()` vise Documents et AppData : sans cette garde, la
    page de statistiques testée afficherait les parties de la personne qui
    fait tourner la suite, et un test passerait ou échouerait selon le poste.
    Un test qui veut des sauvegardes les pose sous ces deux dossiers.
    """
    racines = {"documents": tmp_path / "Documents",
               "localappdata": tmp_path / "AppData" / "Local"}
    monkeypatch.setattr("src.core.sauvegardes.racines", lambda: racines)
    yield


@pytest.fixture(autouse=True)
def _documents_hors_du_vrai_dossier(tmp_path, monkeypatch):
    """Aucun test n'écrit dans le VRAI dossier Documents.

    Le lancement d'un jeu y écrit : `Running.ini`, les patchs d'INI, et depuis
    le 2026-09-24 la configuration réglée qu'il recopie quand elle a disparu
    (`pre_launch.restaurer_configs_manquantes`). Les tests existants
    neutralisaient ces étapes UNE PAR UNE, par leur nom : une étape ajoutée
    sans compléter la liste aurait écrit chez la personne qui lance la suite.
    Même dossier que `_sauvegardes_hors_du_vrai_disque`, pour qu'un test ne
    voie qu'un seul Documents. Un test qui veut le sien le pose par-dessus.
    """
    documents = tmp_path / "Documents"
    for module in ("src.core.post_install", "src.core.pre_launch"):
        monkeypatch.setattr(module + ".get_documents_dir", lambda: documents)
    yield


@pytest.fixture(autouse=True)
def _jamais_d_elevation_uac(monkeypatch):
    """Aucun test ne doit pouvoir faire apparaître une invite UAC.

    `game_registry._ecrire_eleve` appelle `ShellExecuteW(..., "runas", ...)`,
    qui ouvre une fenêtre de consentement Windows et **bloque jusqu'à ce qu'un
    humain clique**. Dans une suite de tests, cela veut dire : une exécution
    qui ne se termine jamais, en CI comme sur le poste de développement, avec
    une boîte de dialogue système au milieu de l'écran.

    Un oubli de bouchon dans UN seul test suffirait. La garde est donc posée
    ici, pour tous : un test qui veut exercer ce chemin doit le remplacer
    explicitement, jamais l'atteindre par accident. Même esprit que la garde
    sur le vrai `config.json` ci-dessus.
    """
    def _interdit(*_a, **_k):
        raise AssertionError(
            "Un test a tenté une écriture registre ÉLEVÉE (invite UAC). "
            "Bouchonner `game_registry.ecrire_valeurs` dans le test.")

    monkeypatch.setattr("src.core.game_registry._ecrire_eleve", _interdit)
    yield


@pytest.fixture(autouse=True)
def _langue_retablie():
    """La langue de l'interface est un état GLOBAL : on la rend après chaque test.

    Construire une `MainWindow` appelle `set_language(config.langue)`, et le
    défaut de `Config.langue` est l'ANGLAIS. Une fixture qui oublie
    `langue="fr"` bascule donc toute la suite en anglais, et ce sont des tests
    SANS RAPPORT, plusieurs fichiers plus loin, qui échouent sur « part 2/3 »
    au lieu de « partie 2/3 ». Payé le 2026-09-18 : un build arrêté par deux
    échecs qui accusaient la barre de téléchargement et le téléchargeur, pour
    une fixture oubliée dans un fichier voisin. Plusieurs fichiers rétablissaient
    déjà le français à la main ; la garde vaut désormais pour tous.
    """
    from src.core.i18n import get_language, set_language
    avant = get_language()
    yield
    if get_language() != avant:
        set_language(avant)


@pytest.fixture(autouse=True)
def _widgets_detruits_a_la_fin_du_test(request, monkeypatch):
    """Les fenêtres d'un test meurent à la fin de CE test, pas n'importe quand.

    pytest-qt ferme chaque widget enregistré puis appelle `deleteLater()`. Mais
    une suppression différée n'est traitée que par une boucle d'événements, et
    `processEvents()` hors boucle ne la traite pas : mesuré le 2026-09-19, les
    `MainWindow` fermées s'accumulaient (jusqu'à six vivantes en C++), puis
    disparaissaient d'un coup quand le ramasse-miettes de Python passait sur
    leurs cycles de références — donc à un instant quelconque, y compris en
    plein `processEvents()` d'un test suivant, pendant qu'une AUTRE fenêtre se
    peignait.

    C'est le seul aléa avéré autour du plantage de la CI Windows (violation
    d'accès dans un `paintEvent`, TestKofiMilestone, deux runs sur deux depuis
    dbdae34, jamais reproduit en local — ni en Python 3.14.7, ni avec un
    ramasse-miettes forcé cinquante fois plus souvent). Le site du plantage
    changeait d'un run à l'autre, signature d'un état corrompu et non du code
    qui peint. Ici, la destruction a lieu à un point sûr : après la fermeture
    par pytest-qt (faite avant les finaliseurs de fixtures), hors de tout
    dessin.

    Le ramasse-miettes n'est forcé qu'après une fenêtre principale ou un
    dialogue : ce sont eux qui portent des cycles de références, et le forcer
    après CHAQUE test Qt coûtait 18 s sur 85.

    Une fenêtre doit aussi VIVRE jusque-là, et rien ne le garantissait.
    pytest-qt ne garde d'un widget enregistré qu'une référence FAIBLE, et il
    fait tourner la boucle d'événements juste après la fin du test, AVANT de
    fermer quoi que ce soit (`pytest_runtest_call`). La variable `win` du test
    n'existe plus à cet instant : une fenêtre encore AFFICHÉE ne tient plus
    qu'à ses cycles de références, et la première allocation venue peut
    déclencher le ramasse-miettes, qui la détruit au milieu de son propre
    dessin. CI Windows 3.12, 2026-09-19 : le premier tick des particules crée
    35 objets, le ramasse-miettes passe, et `self.height()` tombe sur un objet
    détruit entre deux lignes du même slot. Reproduit à coup sûr en 3.12 comme
    en 3.14, en forçant un passage du ramasse-miettes dans ce tick : 1 échec et
    20 erreurs sur `test_integration_smoke.py` seul. Chaque widget enregistré
    est donc tenu ici jusqu'à sa destruction.
    """
    if "qtbot" not in request.fixturenames:
        yield
        return
    from pytestqt.qtbot import QtBot
    tenus = []
    vrai_add_widget = QtBot.addWidget

    def _add_widget_tenu(self, widget, **kwargs):
        vrai_add_widget(self, widget, **kwargs)
        tenus.append(widget)

    monkeypatch.setattr(QtBot, "addWidget", _add_widget_tenu)
    yield
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication, QDialog, QMainWindow
    app = QApplication.instance()
    if app is None:
        return
    lourde = any(isinstance(w, (QMainWindow, QDialog)) for w in app.topLevelWidgets())
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    # Relâchées APRÈS la destruction C++ : il ne reste plus que des enveloppes
    # Python vides, que le ramasse-miettes peut prendre quand il veut.
    tenus.clear()
    if lourde:
        gc.collect()


@pytest.fixture(autouse=True)
def _jamais_le_vrai_discord(monkeypatch):
    """Aucun test ne parle au client Discord de la machine.

    Chaque fin de partie simulée envoie `clear()` à la présence Discord, dont
    le thread ouvre le tube IPC local. Sur un poste où Discord tourne — celui
    de Ludo —, la suite se connectait donc au VRAI client et effaçait l'activité
    affichée sur son profil ; sur le runner, sans Discord, le même code prenait
    un autre chemin. Un test ne doit ni toucher un programme réel, ni se
    comporter différemment selon ce qui tourne à côté. Les tests du protocole
    (`test_discord_presence.py`) posent leur propre faux tube par-dessus.
    """
    monkeypatch.setattr("src.core.discord_presence._open_ipc", lambda: None)
    yield


@pytest.fixture(autouse=True)
def _linux_pret_a_jouer(tmp_path_factory, monkeypatch):
    """Par défaut, les tests voient une machine où les jeux PEUVENT démarrer.

    Sous Windows, c'est le cas du runner : Visual C++ y est installé, et le
    bandeau de la fiche reste caché. Sous Linux, l'équivalent est un lanceur
    de compatibilité, un préfixe initialisé et ses composants en place. Sans
    cette garde, la même suite se comporterait autrement selon la machine :
    « Wine introuvable » sur le runner (qui n'a pas Wine), et un VRAI wine
    lancé sur un poste qui l'a — même esprit que `_jamais_le_vrai_discord`.

    Le lanceur est factice et son chemin n'existe pas : un test qui oublierait
    de remplacer `Popen` échouerait franchement au lieu de lancer quoi que ce
    soit. Le `_Launcher/` de `compat` (préfixes, journaux Wine) vit dans un
    dossier temporaire À PART, propre à CE test : dans `tmp_path`, il se
    serait mêlé à ce que les autres tests y listent. Un test qui veut une
    autre machine le dit : `sans_lanceur`, ou il vide le `winetricks.log`.

    Les contrôles de prérequis sont mémorisés pour la session : on les oublie
    avant et après, sans quoi le résultat d'un test déborderait sur le suivant.
    """
    from src.core import compat, system_checks
    faux = compat.Lanceur("wine", "/nonexistent/accio-test/wine")
    monkeypatch.setattr("src.core.compat.lanceur", lambda: faux)
    racine = tmp_path_factory.mktemp("_Launcher")
    monkeypatch.setattr("src.core.compat._donnees_launcher", lambda: racine)
    pfx = compat.prefixe("wine")
    (pfx / "drive_c").mkdir(parents=True, exist_ok=True)
    (pfx / "system.reg").write_text("WINE REGISTRY Version 2\n\n#arch=win64\n",
                                    encoding="utf-8")
    (pfx / "winetricks.log").write_text("vcrun2022\nvcrun2005\nvcrun2008\n",
                                        encoding="utf-8")
    system_checks.invalidate_vcredist_cache()
    yield faux
    system_checks.invalidate_vcredist_cache()


@pytest.fixture
def lanceur_factice(_linux_pret_a_jouer):
    """Le lanceur factice de la garde ci-dessus, pour un test qui s'en sert."""
    return _linux_pret_a_jouer


@pytest.fixture
def sans_lanceur(monkeypatch):
    """Une machine Linux sans umu-run ni wine : rien ne peut démarrer."""
    from src.core import system_checks
    monkeypatch.setattr("src.core.compat.lanceur", lambda: None)
    system_checks.invalidate_vcredist_cache()
    yield
    system_checks.invalidate_vcredist_cache()


@pytest.fixture
def registre_atteignable(monkeypatch):
    """Un registre présent, quelle que soit la plateforme qui joue la suite.

    Les tests de LANGUE DE JEU exercent la logique qui décide quoi écrire
    (choix, détection, défaut, valeurs communes, prévenance) en bouchonnant
    lecture et écriture. Mais cette logique commence par demander à
    `game_registry.disponible()` s'il y a un registre, et hors Windows la
    réponse est non : sélecteur éteint, rien à écrire, par conception. Sans
    cette fixture, la suite Linux ne testait donc pas une logique cassée — elle
    testait l'ABSENCE de logique, et 25 tests échouaient pour de bon depuis le
    2026-08-22 (job `linux-smoke`, rouge et non bloquant, donc vu de personne).

    Le jour du portage, `disponible()` répondra oui sous Wine : ces tests
    décrivent déjà ce qui devra marcher. `lire_valeurs` et `ecrire_valeurs`
    gardent leur propre test de plateforme, donc forcer la réponse ici
    n'atteint jamais `winreg` sous Linux.
    """
    monkeypatch.setattr("src.core.game_registry.disponible", lambda: True)
