"""Pose vgmstream (musique de HP5 et HP6) dans `assets/vgmstream/`, vérifié.

Les binaires ne sont plus suivis par git depuis le 2026-10-25 : Scorecard
signalait chacun (« Binary-Artifacts », 12 alertes), parce qu'un binaire posé
dans un dépôt ne dit pas d'où il vient. Ils viennent de la release officielle
r2117 (`vgmstream-win64.zip`, licence ISC, `License.txt` = son `COPYING`) ;
ce script la télécharge et vérifie l'empreinte du zip PUIS celle de chaque
fichier, les mêmes octets que ceux qui étaient suivis.

Déjà en place et intacts : rien n'est téléchargé. `build.bat` et la CI Windows
l'appellent avant les tests (`tests/test_vgmstream.py` exige l'exécutable) ;
Linux n'embarque rien, il prend le `vgmstream-cli` du système.
"""

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

DOSSIER = Path(__file__).parent.parent / "assets" / "vgmstream"
URL = "https://github.com/vgmstream/vgmstream/releases/download/r2117/vgmstream-win64.zip"
EMPREINTE_ZIP = "6c4a8a3813864fefed081bbd337dbc0ad93bf88e0b92f5db98d7ab258b22dc6c"
FICHIERS = {
    "avcodec-vgmstream-59.dll": "4d6cf54e7b3c26ef06e95bdb515a10d1e1bed3ec1ffd87ec3e5c4fbcd2a883f6",
    "avformat-vgmstream-59.dll": "0dde66ea268cccb67b1aa219c1ce879602b839e561a79a00c8215e2688f1a4b2",
    "avutil-vgmstream-57.dll": "a999856c17cfdce3c22b92b6640a7ada6c4ab4c3c6841a863770b72fa0bc19b4",
    "libatrac9.dll": "fe82f1ae13a798337e03942c35351997c23caadb5eb0c6b7a2dc2a521ed8b02e",
    "libcelt-0061.dll": "542254723d9100f91cbf18e41c4aff80287c22a9859e9e545c413d984df440ad",
    "libcelt-0110.dll": "bfcc51d865bb3b6a2793381bf535f23ec423feb722b46333fa8556ccdcafa61a",
    "libg719_decode.dll": "aad61f205ce1f1b61285f6b37b90a331ec8c6ae2f94f361714dc21a12c236960",
    "libmpg123-0.dll": "db9eb1d91b8eb9f47b0968201dbf6c51a9627e539a78afd9ad5f59c5d18fe4df",
    "libspeex-1.dll": "04dbc85fcec6c54671535bf39937a70f2dd040a81ad670a0b84de6ca17b39bff",
    "libvorbis.dll": "5f330a20b19b3c70dc43eedcc95891e65940fca04a77155c573efcdd4c2ca665",
    "swresample-vgmstream-4.dll": "688a81d31ef98a9a6143e1075b2f4c5b79bdfa51e7a14d50d662a0e916dac739",
    "vgmstream-cli.exe": "29df08c557ada8269c92a6abfe3886ad2f65849b0b26ba78a0819b363bbc5b85",
}


def _empreinte(donnees: bytes) -> str:
    return hashlib.sha256(donnees).hexdigest()


def _a_poser() -> list[str]:
    return [nom for nom, attendu in FICHIERS.items()
            if not (DOSSIER / nom).is_file() or _empreinte((DOSSIER / nom).read_bytes()) != attendu]


def main() -> int:
    manquants = _a_poser()
    if not manquants:
        print("vgmstream r2117 en place, empreintes vérifiées.")
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
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        contenus = {nom: zf.read(nom) for nom in manquants}
    for nom, donnees in contenus.items():
        if _empreinte(donnees) != FICHIERS[nom]:
            print(f"ERREUR : empreinte de {nom} inattendue dans le zip, rien n'est posé.")
            return 1
    for nom, donnees in contenus.items():
        (DOSSIER / nom).write_bytes(donnees)
    print(f"vgmstream r2117 posé ({len(manquants)} fichier(s)), empreintes vérifiées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
