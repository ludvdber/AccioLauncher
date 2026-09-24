"""Garde AST : aucun slot de fin ne détruit son `QThread` sans l'avoir attendu.

Le défaut (cf. `test_fin_de_thread.py`, `thread_utils.liberer_apres_fin`) : un
signal de fin NOMMÉ part de `run()` juste avant son retour, et le slot qui le
reçoit détruisait l'émetteur — `deleteLater()` nu, ou référence oubliée alors
qu'il restait enfant d'un objet qui allait mourir. Qt abandonne alors le
processus. Il a existé à QUATRE endroits (préparation de Wine, file des
bandes-annonces, `GameOperations`, `UpdateDispatcher`) : ce balayage empêche
le cinquième.

Règle vérifiée, pour chaque `<émetteur>.<signal de fin>.connect(self.<slot>)`
du dépôt, sur le slot ET les méthodes de la classe qu'il appelle :

- un `deleteLater()` n'est permis que sous un `if …wait(…)` ;
- oublier l'émetteur (`self._x = None`) exige une attente dont le résultat est
  LU — `liberer_apres_fin(…)`, ou un `wait()` qui n'est pas une instruction nue.

Analyse statique, sans Qt : elle tourne partout, y compris sans pytest-qt.
"""

import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Convention du projet : un signal de fin est NOMMÉ, jamais `finished`.
# `error` en est un aussi : il part de run() juste avant le retour.
MOTIF_FIN = re.compile(r"(_finished|_terminee)$|^(result|error)$")
AIDE = "liberer_apres_fin"


def _sources() -> dict[Path, str]:
    fichiers = sorted((RACINE / "src").rglob("*.py")) + [RACINE / "main.py"]
    return {f: f.read_text(encoding="utf-8") for f in fichiers}


def _signaux_de_fin(sources) -> dict[str, set[str]]:
    """{classe QThread: {signaux de fin}} relevés dans les définitions."""
    trouves: dict[str, set[str]] = {}
    for texte in sources.values():
        for cls in ast.walk(ast.parse(texte)):
            if not isinstance(cls, ast.ClassDef):
                continue
            if not any(getattr(b, "id", getattr(b, "attr", None)) == "QThread"
                       for b in cls.bases):
                continue
            noms = set()
            for st in cls.body:
                if (isinstance(st, ast.Assign) and isinstance(st.value, ast.Call)
                        and getattr(st.value.func, "id", None) == "pyqtSignal"):
                    noms |= {t.id for t in st.targets
                             if isinstance(t, ast.Name) and MOTIF_FIN.search(t.id)}
            trouves[cls.name] = noms
    return trouves


def _attr_de_self(noeud) -> str | None:
    if (isinstance(noeud, ast.Attribute) and isinstance(noeud.value, ast.Name)
            and noeud.value.id == "self"):
        return noeud.attr
    return None


def _parents(arbre) -> dict:
    return {enfant: parent for parent in ast.walk(arbre)
            for enfant in ast.iter_child_nodes(parent)}


def _est_wait(noeud) -> bool:
    return (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
            and noeud.func.attr == "wait")


def _oublie(noeud, emetteur: str) -> bool:
    """`self.<emetteur> = None`, y compris dans un échange de tuple."""
    if not isinstance(noeud, ast.Assign):
        return False
    for cible in noeud.targets:
        if _attr_de_self(cible) == emetteur and isinstance(noeud.value, ast.Constant) \
                and noeud.value.value is None:
            return True
        if isinstance(cible, ast.Tuple) and isinstance(noeud.value, ast.Tuple):
            for c, v in zip(cible.elts, noeud.value.elts):
                if _attr_de_self(c) == emetteur and isinstance(v, ast.Constant) \
                        and v.value is None:
                    return True
    return False


def _atteignables(methodes: dict, depart: str) -> list[ast.FunctionDef]:
    vues, pile = set(), [depart]
    while pile:
        nom = pile.pop()
        if nom in vues or nom not in methodes:
            continue
        vues.add(nom)
        for n in ast.walk(methodes[nom]):
            if isinstance(n, ast.Call) and _attr_de_self(n.func) in methodes:
                pile.append(n.func.attr)
    return [methodes[n] for n in sorted(vues)]


def analyser(texte: str, fichier: str, signaux: set[str]) -> tuple[list, list]:
    """Rend (connexions examinées, violations) pour un fichier."""
    arbre = ast.parse(texte)
    parents = _parents(arbre)
    connexions, violations = [], []
    for cls in ast.walk(arbre):
        if not isinstance(cls, ast.ClassDef):
            continue
        methodes = {f.name: f for f in cls.body if isinstance(f, ast.FunctionDef)}
        for n in ast.walk(cls):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "connect" and n.args
                    and isinstance(n.func.value, ast.Attribute)
                    and n.func.value.attr in signaux):
                continue
            slot = _attr_de_self(n.args[0])
            if slot not in methodes:
                continue
            emetteur = _attr_de_self(n.func.value.value)
            ou = f"{fichier}:{cls.name}.{slot} ({n.func.value.attr})"
            connexions.append(ou)
            corps = _atteignables(methodes, slot)
            noeuds = [x for f in corps for x in ast.walk(f)]
            protege = any(
                (isinstance(x, ast.Call) and getattr(x.func, "id", None) == AIDE)
                or (_est_wait(x) and not isinstance(parents.get(x), ast.Expr))
                for x in noeuds)
            for x in noeuds:
                if (isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                        and x.func.attr == "deleteLater"):
                    p, garde = parents.get(x), False
                    while p is not None and not garde:
                        garde = isinstance(p, ast.If) and any(
                            _est_wait(t) for t in ast.walk(p.test))
                        p = parents.get(p)
                    if not garde:
                        violations.append(f"{ou} : deleteLater() sans wait() lu, "
                                          f"ligne {x.lineno}")
                if emetteur and _oublie(x, emetteur) and not protege:
                    violations.append(f"{ou} : self.{emetteur} oublié sans attendre "
                                      f"le thread, ligne {x.lineno}")
    return connexions, violations


def _tout_signal(sources) -> set[str]:
    return set().union(*_signaux_de_fin(sources).values())


class TestGardeFinDeThread:
    def test_chaque_qthread_declare_un_signal_de_fin_reconnu(self):
        """Sinon un nouveau thread échapperait au balayage sans bruit."""
        par_classe = _signaux_de_fin(_sources())
        assert {"Downloader", "Installer", "PreparationWine", "DiskScanWorker",
                "UpdateChecker"} <= set(par_classe)
        sans = [c for c, s in par_classe.items() if not s and c != "UpdateChecker"]
        # UpdateChecker n'a pas de fin nommée : on l'attend par son `finished`
        # natif, qui part APRÈS le retour de run() — sans danger.
        assert not sans, f"QThread sans signal de fin reconnu : {sans}"

    def test_aucun_slot_de_fin_ne_detruit_son_thread_sans_l_attendre(self):
        sources = _sources()
        signaux = _tout_signal(sources)
        toutes, fautes = [], []
        for f, texte in sources.items():
            c, v = analyser(texte, f.relative_to(RACINE).as_posix(), signaux)
            toutes += c
            fautes += v
        # Le balayage doit VOIR les sites connus, sinon il passe à vide.
        attendus = ["preparateur_wine.py:PreparateurWine._on_terminee",
                    "trailer_store.py:TrailerStore._on_finished",
                    "trailer_store.py:TrailerStore._on_error",
                    "game_operations.py:GameOperations._on_download_finished",
                    "game_operations.py:GameOperations._on_download_error",
                    "game_operations.py:GameOperations._on_install_finished",
                    "game_operations.py:GameOperations._on_install_error",
                    "update_dispatcher.py:UpdateDispatcher._on_finished",
                    "update_dispatcher.py:UpdateDispatcher._on_error",
                    "settings_panel.py:SettingsDialog._on_scan_done"]
        for a in attendus:
            assert any(a in c for c in toutes), f"balayage aveugle : {a} non vu"
        assert not fautes, "\n".join(fautes)


class TestContreEpreuve:
    """La garde doit refuser l'ancien code — sinon elle ne garde rien."""

    def _violations(self, relatif: str, avant: str, apres: str) -> list:
        sources = _sources()
        texte = (RACINE / relatif).read_text(encoding="utf-8")
        assert texte.count(avant) == 1, f"{relatif} a changé : contre-épreuve à revoir"
        return analyser(texte.replace(avant, apres), relatif, _tout_signal(sources))[1]

    def test_ancien_preparateur_wine(self):
        """`fil.deleteLater()` nu — le code qui plantait en CI Linux."""
        v = self._violations("src/ui/preparateur_wine.py",
                             "liberer_apres_fin(fil)", "fil.deleteLater()")
        assert any("_on_terminee" in x and "deleteLater" in x for x in v), v

    def test_ancien_preparateur_wine_wait_jete(self):
        """Attendre sans lire le résultat ne protège de rien."""
        v = self._violations("src/ui/preparateur_wine.py", "liberer_apres_fin(fil)",
                             "fil.wait(5000)\n            fil.deleteLater()")
        assert any("_on_terminee" in x for x in v), v

    def test_ancienne_reference_oubliee(self):
        """`GameOperations` : référence oubliée, thread resté enfant."""
        v = self._violations("src/ui/game_operations.py",
                             "            liberer_apres_fin(dl)\n", "")
        assert any("_on_download_finished" in x and "oublié" in x for x in v), v
