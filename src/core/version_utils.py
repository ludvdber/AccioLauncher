"""Utilitaires de comparaison de versions sémantiques."""


def compare_versions(a: str, b: str) -> int:
    """Compare deux versions sémantiques. Retourne >0 si a > b, <0 si a < b, 0 si égales."""
    def _parts(v: str) -> list[int]:
        return [int(x) for x in v.lstrip("v").split(".") if x.isdigit()]
    pa, pb = _parts(a), _parts(b)
    while len(pa) < len(pb):
        pa.append(0)
    while len(pb) < len(pa):
        pb.append(0)
    for x, y in zip(pa, pb):
        if x != y:
            return x - y
    return 0
