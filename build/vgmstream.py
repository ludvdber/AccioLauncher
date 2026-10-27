"""Pose vgmstream (musique de HP5 et HP6) dans `assets/vgmstream/`, vérifié : pour les SOURCES.

Les binaires ne sont plus suivis par git depuis le 2026-10-25 : Scorecard
signalait chacun (« Binary-Artifacts », 12 alertes), parce qu'un binaire posé
dans un dépôt ne dit pas d'où il vient. Ils viennent de la release officielle
r2117 (`vgmstream-win64.zip`, licence ISC, `License.txt` = son `COPYING`) ;
ce script la télécharge et vérifie l'empreinte du zip PUIS celle de chaque
fichier. URL et empreintes : `src/core/vgmstream.py`, la même source que le
téléchargement à la première écoute.

Depuis la 1.3.1 (2026-10-28), l'exe ne l'embarque plus : le launcher le
télécharge quand un joueur écoute HP5 ou HP6. Ce dossier sert à lancer et
tester depuis les sources (`tests/test_vgmstream.py` exige l'exécutable) ;
`build.bat` et la CI Windows l'appellent avant les tests. Déjà en place et
intacts : rien n'est téléchargé.
"""

import sys
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from src.core.vgmstream import EMPREINTE_ZIP, FICHIERS, URL, VERSION, _empreinte  # noqa: E402

DOSSIER = RACINE / "assets" / "vgmstream"
# Nom posé → empreinte.
POSES = dict(FICHIERS.values())


def _a_poser() -> list[str]:
    return [nom for nom, attendu in POSES.items()
            if not (DOSSIER / nom).is_file() or _empreinte((DOSSIER / nom).read_bytes()) != attendu]


def main() -> int:
    import io
    import zipfile
    manquants = _a_poser()
    if not manquants:
        print(f"vgmstream {VERSION} en place, empreintes vérifiées.")
        return 0
    print(f"vgmstream : {len(manquants)} fichier(s) à poser, téléchargement de {URL}")
    try:
        with urllib.request.urlopen(URL, timeout=120) as reponse:  # nosec B310 : URL fixe en https
            archive = reponse.read()
    except OSError as exc:
        print(f"ERREUR : vgmstream n'a pas pu être téléchargé : {exc}")
        return 1
    if _empreinte(archive) != EMPREINTE_ZIP:
        print("ERREUR : l'empreinte de vgmstream-win64.zip ne correspond pas, rien n'est posé.")
        return 1
    dans_le_zip = {pose: nom for nom, (pose, _e) in FICHIERS.items()}
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        contenus = {pose: zf.read(dans_le_zip[pose]) for pose in manquants}
    for pose, donnees in contenus.items():
        if _empreinte(donnees) != POSES[pose]:
            print(f"ERREUR : empreinte de {pose} inattendue dans le zip, rien n'est posé.")
            return 1
    DOSSIER.mkdir(parents=True, exist_ok=True)
    for pose, donnees in contenus.items():
        (DOSSIER / pose).write_bytes(donnees)
    print(f"vgmstream {VERSION} posé ({len(manquants)} fichier(s)), empreintes vérifiées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
