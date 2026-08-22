#!/usr/bin/env python
"""Écrit le bloc `trailers` d'un games.json à partir d'une release GitHub.

Les bandes-annonces ne sont plus dans l'exécutable : elles sont publiées en
assets de release et déclarées par le catalogue, qui se met à jour à distance.
Ce script fait la déclaration — pour qu'aucune URL ni aucune taille ne soit
recopiée à la main.

Trois choses qu'il ne faut pas saisir soi-même :

* **l'URL** : elle se déduit du tag et du nom de fichier, une faute de frappe
  donne un 404 silencieux au premier utilisateur qui accepte les vidéos ;
* **la taille** : `size_mb` sert de PLAFOND au téléchargement
  (`SIZE_OVERHEAD_FACTOR`, ×1,5). Sous-estimée, elle fait avorter un
  téléchargement parfaitement sain ;
* **la liste** : n'y déclarer que ce qui EXISTE. Annoncer huit vidéos dont six
  répondent 404 fait six échecs à chaque tentative.

Usage :
    python tools/sync_trailers.py src/data/games.json
    python tools/sync_trailers.py src/data/games.json ../accio-launcher-games/games.json
    python tools/sync_trailers.py --tag trailers-v2 --version 2.0 --bump src/data/games.json

Sans `--version`, les jeux déjà déclarés gardent la leur (on ne re-versionne
pas huit vidéos parce qu'on en a ajouté une) et les nouveaux prennent « 1.0 ».
Le script est idempotent : rejoué sans changement, il ne réécrit rien.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEPOT = "ludvdber/accio-launcher-games"
TAG_DEFAUT = "trailers-v1"
VERSION_DEFAUT = "1.0"

# Le nom de l'asset ne porte PAS la version : c'est le fichier local qui la
# porte (`hp1_video_v1.0.mp4`), sans quoi une bande-annonce améliorée ne
# remplacerait jamais l'ancienne. Voir `src/core/trailers.py`.
_ASSET = re.compile(r"^(?P<id>[A-Za-z0-9][A-Za-z0-9._-]*)_video\.mp4$")


def lire_release(depot: str, tag: str) -> list[dict]:
    """Assets de la release `tag`. Lève SystemExit avec un message utile."""
    url = f"https://api.github.com/repos/{depot}/releases/tags/{tag}"
    requete = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "accio-sync-trailers",
    })
    try:
        with urllib.request.urlopen(requete, timeout=30) as reponse:
            donnees = json.load(reponse)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SystemExit(
                f"Aucune release taguée « {tag} » sur {depot}.\n"
                "Une release BROUILLON n'est pas visible par l'API : publiez-la "
                "d'abord, ou corrigez le tag avec --tag.") from exc
        raise SystemExit(f"GitHub a répondu {exc.code} : {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Réseau indisponible : {exc.reason}") from exc
    assets = donnees.get("assets")
    return assets if isinstance(assets, list) else []


def bloc_trailers(assets: list[dict], anciens: dict, version: str | None) -> tuple[dict, list[str]]:
    """(nouveau bloc `trailers`, noms d'assets ignorés)."""
    trailers: dict[str, dict] = {}
    ignores: list[str] = []
    for asset in assets:
        nom = asset.get("name", "")
        correspondance = _ASSET.match(nom)
        if correspondance is None:
            ignores.append(nom)
            continue
        jeu = correspondance.group("id")
        octets = int(asset.get("size") or 0)
        ancien = anciens.get(jeu) if isinstance(anciens.get(jeu), dict) else {}
        trailers[jeu] = {
            "version": version or str(ancien.get("version") or VERSION_DEFAUT),
            "url": asset.get("browser_download_url", ""),
            # Arrondi au SUPÉRIEUR : `size_mb` est un plafond, et un plafond
            # arrondi vers le bas coupe le téléchargement qu'il devait protéger.
            "size_mb": -(-octets // (1024 * 1024)),
        }
    return trailers, ignores


def ecrire(chemin: Path, trailers: dict, bump: bool) -> bool:
    """Pose le bloc dans le fichier. Retourne True s'il a changé."""
    # `newline=""` est indispensable : sans lui Python traduit les CRLF en
    # LF à la LECTURE, la détection ci-dessous conclut « LF » et le fichier
    # ressort reformaté de bout en bout.
    brut = chemin.read_text(encoding="utf-8", newline="")
    # Réécrire avec la MISE EN FORME reçue : le dépôt du catalogue est en CRLF
    # indenté à 4 espaces, et reformater noierait la vraie modification.
    fin_de_ligne = "\r\n" if "\r\n" in brut else "\n"
    indentation = re.search(r'^([ \t]+)"', brut, re.MULTILINE)
    indent = len(indentation.group(1)) if indentation else 2
    catalogue = json.loads(brut)

    if catalogue.get("trailers") == trailers and not bump:
        return False
    catalogue["trailers"] = trailers
    if bump:
        actuelle = str(catalogue.get("catalog_version", "0.0"))
        majeur, _, mineur = actuelle.partition(".")
        catalogue["catalog_version"] = f"{majeur}.{int(mineur or 0) + 1}"

    # ensure_ascii=False est OBLIGATOIRE : sinon les accents partent en \uXXXX
    # et le fichier devient illisible en revue de PR.
    with open(chemin, "w", encoding="utf-8", newline=fin_de_ligne) as f:
        f.write(json.dumps(catalogue, ensure_ascii=False, indent=indent) + "\n")
    return True


def main(argv: list[str]) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("catalogues", nargs="+", type=Path,
                         help="chemins de games.json à mettre à jour")
    parseur.add_argument("--tag", default=TAG_DEFAUT, help=f"tag de la release (défaut : {TAG_DEFAUT})")
    parseur.add_argument("--depot", default=DEPOT, help=f"dépôt GitHub (défaut : {DEPOT})")
    parseur.add_argument("--version", default=None,
                         help="version à écrire pour TOUTES les bandes-annonces")
    parseur.add_argument("--bump", action="store_true",
                         help="incrémente aussi catalog_version")
    args = parseur.parse_args(argv[1:])

    for chemin in args.catalogues:
        if not chemin.is_file():
            print(f"Introuvable : {chemin}", file=sys.stderr)
            return 2

    assets = lire_release(args.depot, args.tag)
    premier = json.loads(args.catalogues[0].read_text(encoding="utf-8"))
    anciens = premier.get("trailers") if isinstance(premier.get("trailers"), dict) else {}
    trailers, ignores = bloc_trailers(assets, anciens, args.version)

    if not trailers:
        print(f"La release « {args.tag} » ne contient aucun fichier <id>_video.mp4.",
              file=sys.stderr)
        return 1

    # Un identifiant qui n'est dans aucun jeu ne sera JAMAIS joué : le catalogue
    # est la seule source de la correspondance jeu → bande-annonce.
    connus = {j.get("id") for j in premier.get("games", []) if isinstance(j, dict)}
    orphelins = sorted(set(trailers) - connus)
    absents = sorted(connus - set(trailers))

    for chemin in args.catalogues:
        change = ecrire(chemin, trailers, args.bump)
        print(f"{chemin} : {'mis à jour' if change else 'déjà à jour'} "
              f"({len(trailers)} bande(s)-annonce(s))")

    total = sum(t["size_mb"] for t in trailers.values())
    print(f"\nRelease « {args.tag} » — {len(trailers)} vidéo(s), {total} Mo au total :")
    for jeu, t in sorted(trailers.items()):
        print(f"  · {jeu:<6} v{t['version']:<6} {t['size_mb']:>5} Mo")
    if ignores:
        print("\nAssets ignorés (nom hors convention <id>_video.mp4) :")
        for nom in ignores:
            print(f"  · {nom}")
    if orphelins:
        print("\nATTENTION — bandes-annonces sans jeu correspondant "
              "(elles ne seront jamais jouées) :")
        for jeu in orphelins:
            print(f"  · {jeu}")
    if absents:
        print(f"\nJeux encore sans bande-annonce : {', '.join(absents)}")
    return 1 if orphelins else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
