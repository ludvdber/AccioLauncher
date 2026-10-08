"""Une seule barrière « chemin relatif sûr » pour tout ce qui vient du dehors.

Le catalogue (distant), l'exécutable que le manager lance et les noms
d'entrées d'archive composent des chemins sur le disque de l'utilisateur. Il y
avait quatre gardes pour ça (`game_data`, `catalogue_blocs`, `game_manager`,
`extractors`), et elles ne refusaient pas la même chose : seule celle du
catalogue voyait l'octet nul et les chemins trop longs, seule celle des
archives voyait « .. » maquillé en « .. » suivi d'une espace, seule celle de
l'exécutable voyait CON ou NUL. Le motif « deux listes qu'aucun calcul ne
relie » (règles 98, 99) ; audit du 2026-10-07, P1-006, ACT-007.

Celle-ci refuse tout ce que refusait au moins l'une d'elles, et chacune
l'appelle. Pure, sans Qt ni disque.
"""

# Noms de périphériques réservés par Windows : ouvrir « CON » ouvre la console,
# pas un fichier — quel que soit le dossier et quelle que soit l'extension.
_PERIPHERIQUES = frozenset(
    ["con", "prn", "aux", "nul"]
    + ["com%d" % i for i in range(1, 10)]
    + ["lpt%d" % i for i in range(1, 10)]
)

# Au-delà, l'API Windows classique échoue de toute façon plus loin : autant
# le dire ici, où la raison est claire.
_LONGUEUR_MAX = 260


def est_peripherique(nom: str) -> bool:
    """True si `nom` est un nom de périphérique Windows réservé."""
    return nom.split(".")[0].strip().lower() in _PERIPHERIQUES


def refus_de_chemin(chemin: str) -> str | None:
    r"""Pourquoi ce chemin ne peut pas être joint au dossier d'un jeu, ou None.

    Les « \ » sont normalisés AVANT de vérifier : sous POSIX ce n'est pas un
    séparateur, et « ..\..\evil.dll » y passait pour un nom ordinaire.
    """
    if not chemin:
        return "vide"
    if "\x00" in chemin:
        return "octet nul"
    if len(chemin) > _LONGUEUR_MAX:
        return f"trop long ({len(chemin)} caractères)"
    norm = chemin.replace("\\", "/")
    if ":" in norm:
        # C:\..., mais aussi « a/C:x » ou « HP.exe:flux » : un deux-points n'est
        # jamais permis dans un nom Windows, et ailleurs qu'en tête il désigne
        # un flux de données alternatif (NTFS).
        return "deux-points"
    if norm.startswith("/"):
        return "absolu"          # /abs, //serveur/partage
    for composant in norm.split("/"):
        if not composant or composant == ".":
            continue
        # « .. », mais aussi « .. » déguisé : Windows retire les points et
        # espaces en fin de nom, et un composant fait seulement de points et
        # d'espaces n'a aucun usage légitime et un sens qui varie d'une API à
        # l'autre. Sur le nom NON rogné : « ./x » précédé d'une espace, c'est « ␠. ».
        if not composant.strip(". "):
            return "remontée"
        if est_peripherique(composant):
            return "nom réservé"
    return None


def chemin_relatif_sur(chemin: str) -> bool:
    """True si ce chemin peut être joint au dossier d'un jeu sans en sortir."""
    return refus_de_chemin(chemin) is None
