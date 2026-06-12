"""Tests pour src/core/i18n.py — intégrité du dictionnaire de traductions."""

import ast
from pathlib import Path

import src.core.i18n as i18n
from src.core.i18n import _EN, set_language, tr


class TestDictIntegrity:
    def test_no_duplicate_keys_in_source(self):
        """Un doublon de clé dans le littéral _EN écrase silencieusement la
        première traduction — interdit (collision du type « Réduire »)."""
        tree = ast.parse(Path(i18n.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # `_EN: dict[str, str] = {...}` est un AnnAssign (cible unique)
            target = None
            if isinstance(node, ast.AnnAssign):
                target = node.target
            elif isinstance(node, ast.Assign) and node.targets:
                target = node.targets[0]
            if (target is not None and isinstance(target, ast.Name)
                    and target.id == "_EN" and isinstance(node.value, ast.Dict)):
                keys = [
                    k.value for k in node.value.keys
                    if isinstance(k, ast.Constant)
                ]
                duplicates = {k for k in keys if keys.count(k) > 1}
                assert not duplicates, f"Clés i18n dupliquées : {duplicates}"
                assert len(keys) > 100  # sanité : on a bien parsé le vrai dico
                return
        raise AssertionError("littéral _EN introuvable dans i18n.py")

    def test_all_values_are_strings(self):
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in _EN.items())

    def test_no_identical_translation(self):
        """Une « traduction » identique à la clé signale souvent un oubli.

        Liste blanche pour les chaînes réellement identiques dans les deux
        langues (mots internationaux, gabarits sans texte).
        """
        allowed = {"Discord", "Version {}", "Versions — {}"}
        identical = {k for k, v in _EN.items() if k == v}
        assert identical <= allowed, f"Traductions identiques à la clé : {identical - allowed}"


class TestTr:
    def test_french_default_passthrough(self):
        set_language("fr")
        assert tr("N'importe quoi d'inconnu") == "N'importe quoi d'inconnu"

    def test_english_lookup_and_fallback(self):
        set_language("en")
        try:
            assert tr("Fermer") == "Close"
            # Clé absente → repli sur le français, jamais de KeyError
            assert tr("Clé totalement inconnue") == "Clé totalement inconnue"
        finally:
            set_language("fr")
