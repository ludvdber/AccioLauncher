"""Tests pour src/core/i18n.py — intégrité et couverture des fichiers de langue.

Les traductions vivent désormais dans `src/data/i18n/<code>.json` (contribuables
sans toucher au Python). Le test central est celui de COUVERTURE : il extrait par
AST tous les `tr("…")` du code et exige une entrée dans chaque langue — c'est ce
qui empêche une chaîne d'apparaître en français au milieu d'une UI anglaise.
"""

import ast
import glob
import json
from pathlib import Path

import pytest

import src.core.i18n as i18n
from src.core.config import I18N_DIR
from src.core.i18n import (
    SOURCE_LANGUAGE, available_languages, detect_system_language, is_supported,
    set_language, tr, translator_credits,
)

# Chaînes réellement identiques dans plusieurs langues (marques, gabarits nus).
IDENTIQUES_TOLEREES = {
    # « Halloween » s'écrit pareil dans les trois langues (la citrouille qui
    # accompagnait la clé a été retirée : U+1F383 sortait en emoji couleur).
    "Discord", "Version {}", "Versions — {}", "Halloween",
    "Quidditch", "Gryffindor", "Slytherin", "Ravenclaw", "Hufflepuff",
    # « restantes » s'écrit pareil en français et en espagnol.
    "~{}s restantes", "~{} min restantes", "~{}h restantes",
    # « changelog » est le même mot en français et en anglais.
    "v{} · changelog",
    # Noms de produits Microsoft : ils ne se traduisent pas.
    "Visual C++ x86", "Visual C++ 2005 x86", "Visual C++ 2008 x86",
    # Abréviations d'unités de durée, identiques en FR/EN/ES. L'abréviation
    # n'est pas une paresse : elle évite l'accord du singulier (« 1 hour » vs
    # « 2 hours »), qu'une grille de statistiques rencontrerait à chaque ligne
    # et qu'un format à trous ne sait pas rendre.
    "{} h", "{} min", "{} h {} min",
    # « < 1 min » n'a rien a traduire : un signe mathematique et une
    # abreviation d'unite, identiques dans les trois langues. C'est la forme
    # courte de « moins d'une minute », reservee a la legende d'une jaquette
    # ou la place se compte en dizaines de pixels.
    "< 1 min",
    # « saga » vient de l'islandais et a fait le tour de l'Europe sans changer :
    # « La saga » s'ecrit a l'identique en francais et en espagnol.
    "La saga",
}

LANG_FILES = sorted(Path(p) for p in glob.glob(str(I18N_DIR / "*.json")))


def _tr_literals(path: str) -> list[str]:
    """Arguments littéraux de tous les appels `tr("…")` d'un fichier."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "tr" and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]


def _source_files() -> list[str]:
    """Tous les fichiers qui peuvent appeler `tr()`.

    **`main.py` en fait partie** et était absent de ce balayage : il porte les
    cinq étapes de l'écran de démarrage — « Initialisation », « Prêt »… —,
    c'est-à-dire le tout premier texte que voit un utilisateur. Elles se
    trouvaient traduites (vérifié le 2026-08-28, aucune manquante), donc ce
    n'était pas un défaut vivant ; mais rien n'obligeait la suivante à l'être.
    Un filet qui laisse passer la première impression n'en est pas un.
    """
    return glob.glob("src/**/*.py", recursive=True) + ["main.py"]


def _source_keys() -> set[str]:
    keys: set[str] = set()
    for path in _source_files():
        keys |= set(_tr_literals(path))
    return keys


def _strings(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))["strings"]


class TestFichiersDeLangue:
    def test_au_moins_deux_langues(self):
        assert len(LANG_FILES) >= 2, "en.json et es.json au minimum"

    @pytest.mark.parametrize("path", LANG_FILES, ids=lambda p: p.stem)
    def test_structure(self, path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(raw.get("_meta"), dict)
        assert raw["_meta"].get("code") == path.stem
        assert raw["_meta"].get("name")
        assert isinstance(raw["_meta"].get("translators"), list)
        assert isinstance(raw.get("strings"), dict)

    @pytest.mark.parametrize("path", LANG_FILES, ids=lambda p: p.stem)
    def test_pas_de_cle_dupliquee(self, path):
        """`json.load` garde SILENCIEUSEMENT la dernière valeur d'une clé répétée.

        Un doublon écraserait donc une traduction sans le moindre signal — il
        faut relire les paires brutes pour le détecter.
        """
        seen: list[str] = []
        json.loads(path.read_text(encoding="utf-8"),
                   object_pairs_hook=lambda pairs: seen.extend(k for k, _ in pairs))
        doublons = {k for k in seen if seen.count(k) > 1}
        assert not doublons, f"Clés dupliquées dans {path.name} : {doublons}"

    @pytest.mark.parametrize("path", LANG_FILES, ids=lambda p: p.stem)
    def test_valeurs_non_vides(self, path):
        vides = [k for k, v in _strings(path).items() if not isinstance(v, str) or not v.strip()]
        assert not vides, f"Traductions vides dans {path.name} : {vides[:5]}"

    @pytest.mark.parametrize("path", LANG_FILES, ids=lambda p: p.stem)
    def test_placeholders_preserves(self, path):
        """Un `{}` perdu à la traduction fait planter le `.format()` appelant."""
        faux = [
            k for k, v in _strings(path).items()
            if k.count("{}") != v.count("{}") or k.count("%p%") != v.count("%p%")
        ]
        assert not faux, f"Placeholders incohérents dans {path.name} : {faux[:5]}"

    @pytest.mark.parametrize("path", LANG_FILES, ids=lambda p: p.stem)
    def test_pas_de_traduction_identique(self, path):
        identiques = {k for k, v in _strings(path).items() if k == v}
        assert identiques <= IDENTIQUES_TOLEREES, (
            f"Traductions identiques à la clé dans {path.name} : "
            f"{identiques - IDENTIQUES_TOLEREES}")


class TestCouverture:
    def test_toutes_les_chaines_du_code_sont_traduites(self):
        """Chaque `tr("…")` du code doit exister dans CHAQUE langue.

        Sans ce test, ajouter un widget sans compléter les fichiers de langue
        laisse une chaîne française au milieu d'une UI anglaise ou espagnole.
        """
        keys = _source_keys()
        assert len(keys) > 150, "extraction AST anormalement pauvre"
        for path in LANG_FILES:
            manquants = keys - set(_strings(path))
            assert not manquants, (
                f"{len(manquants)} chaîne(s) sans traduction dans {path.name} : "
                f"{sorted(manquants)[:5]}")


class TestPasDeClesOrphelines:
    """Aucune clé de traduction ne doit survivre au texte qu'elle traduisait.

    **34 clés mortes s'étaient accumulées** (audit du 2026-08-28) : l'ancien
    tableau de bord des statistiques, le réglage « vérifier au démarrage »
    supprimé, et une dizaine de formulations remplacées. Rien ne les voyait —
    `TestCouverture` vérifie le sens INVERSE (toute chaîne du code est
    traduite), et ce sens-là ne dit jamais qu'une clé ne sert plus.

    Le coût n'est pas le poids du fichier : c'est qu'un traducteur bénévole
    traduit ces lignes-là aussi. Lui faire dépenser son temps sur des chaînes
    que personne ne verra est la meilleure façon de ne pas en recevoir une
    seconde contribution.

    La clé doit apparaître comme LITTÉRAL quelque part dans `src/`, pas
    forcément dans un `tr()` : certaines sont résolues dynamiquement — les noms
    de maison (`tr(palette.nom)`) et les formes singulier/pluriel du compteur
    de téléchargements. Chercher dans le TEXTE des sources ne marcherait pas :
    les commentaires citent « Serpentard » ou « Gryffondor » sans les employer.
    """

    @staticmethod
    def _litteraux_du_code() -> set:
        litteraux = set()
        for chemin in _source_files():
            arbre = ast.parse(Path(chemin).read_text(encoding="utf-8"))
            for n in ast.walk(arbre):
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    litteraux.add(n.value)
        return litteraux

    def test_chaque_cle_correspond_a_une_chaine_du_code(self):
        litteraux = self._litteraux_du_code()
        assert len(litteraux) > 200, "extraction AST anormalement pauvre"
        for path in LANG_FILES:
            orphelines = sorted(set(_strings(path)) - litteraux)
            assert not orphelines, (
                f"{len(orphelines)} clé(s) orpheline(s) dans {path.name} — "
                f"le texte qu'elles traduisaient n'existe plus : "
                f"{orphelines[:5]}")

    def test_les_cles_resolues_dynamiquement_survivent(self):
        """Contre-épreuve du test précédent : il ne doit pas se contenter des
        `tr()` littéraux, sinon il exigerait la suppression de clés VIVANTES."""
        litteraux = self._litteraux_du_code()
        for cle in ("Gryffondor", "Serpentard", "Poudlard (or)",
                    "{} téléchargement", "{} téléchargements"):
            assert cle in litteraux, f"{cle!r} est pourtant utilisée"


class TestTr:
    def test_francais_est_la_source(self):
        set_language(SOURCE_LANGUAGE)
        assert tr("N'importe quoi d'inconnu") == "N'importe quoi d'inconnu"

    def test_anglais(self):
        set_language("en")
        try:
            assert tr("Fermer") == "Close"
        finally:
            set_language(SOURCE_LANGUAGE)

    def test_espagnol(self):
        set_language("es")
        try:
            assert tr("Fermer") == "Cerrar"
        finally:
            set_language(SOURCE_LANGUAGE)

    def test_cle_absente_ne_leve_jamais(self):
        set_language("es")
        try:
            assert tr("Clé totalement inconnue") == "Clé totalement inconnue"
        finally:
            set_language(SOURCE_LANGUAGE)

    def test_langue_inconnue_retombe_sur_la_source(self):
        set_language("kl")
        try:
            assert tr("Fermer") == "Fermer"
        finally:
            set_language(SOURCE_LANGUAGE)


class TestDecouverte:
    def test_le_francais_est_en_tete(self):
        langues = available_languages()
        assert langues[0].code == SOURCE_LANGUAGE

    def test_en_et_es_sont_proposes(self):
        codes = {info.code for info in available_languages()}
        assert {"fr", "en", "es"} <= codes

    def test_is_supported(self):
        assert is_supported("es")
        assert not is_supported("kl")

    def test_credits_excluent_la_source(self):
        noms = {nom for nom, _ in translator_credits()}
        assert "Français" not in noms
        assert noms, "au moins une langue traduite doit créditer quelqu'un"

    def test_detection_systeme_retourne_une_langue_supportee(self):
        assert is_supported(detect_system_language())


class TestSurchargeUtilisateur:
    """Fichier déposé dans ~/Games/AccioLauncher/i18n/ — workflow du traducteur.

    C'est ce qui permet à un contributeur de voir sa traduction dans le vrai
    launcher sans attendre une release. Si ce mécanisme casse, le guide de
    docs/TRANSLATORS.md ment.
    """

    @pytest.fixture
    def user_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "USER_I18N_DIR", tmp_path)
        i18n._reset_for_tests()
        yield tmp_path
        i18n._reset_for_tests()
        set_language(SOURCE_LANGUAGE)

    @staticmethod
    def _write(path: Path, code: str, name: str, strings: dict, translators=("Moi",)):
        (path / f"{code}.json").write_text(
            json.dumps({"_meta": {"code": code, "name": name,
                                  "translators": list(translators)},
                        "strings": strings}, ensure_ascii=False),
            encoding="utf-8")

    def test_nouvelle_langue_decouverte(self, user_dir):
        self._write(user_dir, "de", "Deutsch", {"Fermer": "Schließen"})
        assert is_supported("de")
        set_language("de")
        assert tr("Fermer") == "Schließen"

    def test_surcharge_partielle_complete_lembarque(self, user_dir):
        """Surcharger une chaîne ne doit pas faire perdre les 210 autres."""
        self._write(user_dir, "es", "Español", {"Fermer": "CERRAR (test)"})
        set_language("es")
        assert tr("Fermer") == "CERRAR (test)"
        assert tr("Annuler") == "Cancelar", "le reste de l'espagnol embarqué survit"

    def test_fichier_illisible_est_ignore(self, user_dir):
        """Un JSON cassé ne doit jamais empêcher le launcher de démarrer."""
        (user_dir / "it.json").write_text("{ pas du json", encoding="utf-8")
        assert not is_supported("it")
        set_language("es")
        assert tr("Fermer") == "Cerrar"

    def test_valeurs_non_texte_ignorees(self, user_dir):
        self._write(user_dir, "pt", "Português", {"Fermer": 42, "Annuler": "Cancelar"})
        set_language("pt")
        assert tr("Fermer") == "Close", "valeur aberrante -> repli anglais"
        assert tr("Annuler") == "Cancelar"

    def test_traducteur_credite(self, user_dir):
        self._write(user_dir, "de", "Deutsch", {"Fermer": "Schließen"},
                    translators=("Ada",))
        credits = dict(translator_credits())
        assert "Ada" in credits.get("Deutsch", ())
