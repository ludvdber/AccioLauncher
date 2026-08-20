"""Utilitaires de comparaison de versions sémantiques."""


def compare_versions(a: str, b: str) -> int:
    """Compare deux versions sémantiques. Retourne >0 si a > b, <0 si a < b, 0 si égales."""
    def _parts(v: str) -> list[int]:
        # Un composant non numérique vaut 0 au lieu d'être SUPPRIMÉ. Le
        # supprimer décalait tous les suivants d'un cran : « 1.beta.5 » se
        # réduisait à [1, 5] et ressortait donc plus récent que « 1.0.5 »
        # (mesuré : +5). Le catalogue étant mis à jour à distance, une coquille
        # de ce genre ne doit pas inverser une comparaison de versions.
        return [int(x) if x.isdigit() else 0 for x in v.lstrip("v").split(".")]
    pa, pb = _parts(a), _parts(b)
    while len(pa) < len(pb):
        pa.append(0)
    while len(pb) < len(pa):
        pb.append(0)
    for x, y in zip(pa, pb):
        if x != y:
            return x - y
    return 0


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
