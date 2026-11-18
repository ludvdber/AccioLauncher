"""Utilitaires de comparaison de versions sémantiques."""
import re

_CHIFFRES = re.compile(r"[0-9]+")


def compare_versions(a: str, b: str) -> int:
    """Compare deux versions sémantiques. Retourne >0 si a > b, <0 si a < b, 0 si égales.

    Une pré-version (« 1.3.6-beta.1 ») vient AVANT sa version (« 1.3.6 ») et
    après la précédente (« 1.3.5 »), comme en SemVer. Lue chiffre à chiffre,
    « 6-beta » valait 0 : la bêta passait pour une 1.3.0.1, et son launcher
    proposait de « mettre à jour » vers la 1.3.5 (2026-11-18).
    """
    def _parts(v: str) -> list[int]:
        # Un composant non numérique vaut 0 au lieu d'être SUPPRIMÉ. Le
        # supprimer décalait tous les suivants d'un cran : « 1.beta.5 » se
        # réduisait à [1, 5] et ressortait donc plus récent que « 1.0.5 »
        # (mesuré : +5). Le catalogue étant mis à jour à distance, une coquille
        # de ce genre ne doit pas inverser une comparaison de versions.
        # Les chiffres ASCII EN TÊTE du composant (audit du 2026-11-16) :
        # « 5rc1 » valait 0, donc « 1.0.5rc1 » < « 1.0.4 » ; et « ² »
        # passe `isdigit()` mais fait lever `int()`.
        return [int(m[0]) if (m := _CHIFFRES.match(x)) else 0 for x in v.split(".")]
    noyau_a, tiret_a, pre_a = a.strip().lstrip("v").partition("+")[0].partition("-")
    noyau_b, tiret_b, pre_b = b.strip().lstrip("v").partition("+")[0].partition("-")
    pa, pb = _parts(noyau_a), _parts(noyau_b)
    while len(pa) < len(pb):
        pa.append(0)
    while len(pb) < len(pa):
        pb.append(0)
    for x, y in zip(pa, pb, strict=True):
        if x != y:
            return x - y
    if tiret_a != tiret_b:
        return -1 if tiret_a else 1
    return _comparer_pre(pre_a, pre_b)


def _comparer_pre(a: str, b: str) -> int:
    """Ordre SemVer des pré-versions : champ par champ, un nombre avant un mot,
    les nombres comme des nombres (« beta.10 » après « beta.9 »), le plus court avant."""
    for x, y in zip(a.split("."), b.split("."), strict=False):
        if x == y:
            continue
        nx, ny = _nombre(x), _nombre(y)
        if nx and ny:
            return int(x) - int(y)
        if nx != ny:
            return -1 if nx else 1
        return -1 if x < y else 1
    return len(a.split(".")) - len(b.split("."))


def _nombre(champ: str) -> bool:
    """Un champ fait de chiffres ASCII seulement (« ² » passe `isdigit()`)."""
    return champ.isascii() and champ.isdigit()


def update_disponible(installee: str | None, recommandee: str) -> bool:
    """True si `recommandee` est STRICTEMENT plus récente que `installee`.

    Source unique de la règle « une mise à jour est disponible ». Elle était
    écrite deux fois — `GameManager.has_update` et `UpdateChecker._check_catalog`
    — et les deux fois en comparaison de CHAÎNES (`installee != recommandee`),
    alors que ce module existe justement pour comparer des NOMBRES. Deux
    conséquences, l'une et l'autre visibles par l'utilisateur :

    - « 1.0 » et « 1.0.0 » sont textuellement différents et numériquement
      identiques : le jour où le catalogue écrit l'un et la config l'autre, une
      mise à jour fantôme s'affichait en permanence, avec un lien qui
      re-téléchargeait la même version ;
    - un retour en arrière du catalogue (recommandée < installée) était
      présenté comme une mise à jour.

    Sans version installée connue, on ne propose rien : c'est le rôle du
    backfill de `GameManager` de lui en attribuer une.
    """
    if not installee or not recommandee:
        return False
    return compare_versions(recommandee, installee) > 0
