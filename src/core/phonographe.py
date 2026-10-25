"""Le phonographe : les musiques des jeux, lues dans la copie du joueur.

Idée validée par Ludo le 2026-10-24. Rien n'est distribué : les morceaux
viennent du dossier du jeu INSTALLÉ, et la Médiathèque les joue
(`ui/mediatheque.py`).

Relevé sur les jeux (atelier, `notes/PHONOGRAPHE_PROJECTION_TRADUCTIONS.md`) :

- **HP2 et HP3** rangent leur musique en fichiers OGG Vorbis ordinaires
  (`Music/*.ogg`, `music/*.ogg`) : le lecteur Qt les lit tels quels.
- **HP1** la range dans des paquets du moteur (`Music/*.umx`), un objet
  `Music` par paquet, dont le format est NOMMÉ dans la table des noms du
  paquet : `mp2` sur les 91 (MPEG-2 couche II). Le flux est recopié octet pour
  octet dans le cache, puis lu comme un fichier ordinaire.
- **HP4** : musique interactive d'EA dans `music.big` (`archives_ea`) : chaque
  `*_stream.mus` met bout à bout des flux SCHl, morceaux et transitions. Les
  flux d'au moins `SEUIL_MORCEAU` octets (≈ 16 s) sont des morceaux ; ceux des
  `sfx` et `amb` sont des ambiances, laissés de côté. Un flux recopié dans le
  cache est un `.asf` qu'FFmpeg lit tel quel.
- **HP5 et HP6** : même rangement (`hog_music_stream.mus`, 53 morceaux ;
  `hbpmusic.mus`, 114), mais en EALayer3, qu'FFmpeg ne lit pas : le flux
  recopié est converti en WAV par `vgmstream`. Sans vgmstream, ces jeux
  n'ont pas de morceaux. Les WAV du cache d'un jeu ne dépassent pas
  `_PLAFOND_WAV` : les plus anciens écoutés partent d'abord.

Aucune fonction ne lève : un paquet abîmé ou d'un autre format est sauté.
"""

import logging
import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.core import archives_ea, vgmstream

log = logging.getLogger(__name__)

# Le dossier de musique (casse ignorée : HP3 l'écrit « music ») et le motif.
_SOURCES: dict[str, tuple[str, str]] = {
    "hp1": ("music", "*.umx"),
    "hp2": ("music", "*.ogg"),
    "hp3": ("music", "*.ogg"),
}
# Les jeux dont la musique vit dans une archive EA (`archives_ea`).
_ARCHIVES: dict[str, str] = {"hp4": "music.big", "hp5": "music.big", "hp6": "music.big"}
# Ceux dont le flux doit passer par vgmstream avant d'être lu.
_A_CONVERTIR = frozenset({"hp5", "hp6"})
_PLAFOND_WAV = 400 << 20
SEUIL_MORCEAU = 700 << 10
_MAGIC_UE1 = 0x9E2A83C1
# Formats que le lecteur sait ouvrir une fois le flux sorti du paquet.
_FORMATS_LISIBLES = frozenset({"mp2", "mp3", "ogg", "wav"})
# Suffixes de travail des compositeurs, retirés du titre affiché.
_SUFFIXES = ("edit", "mx", "music", "loop", "withloop")


@dataclass(frozen=True, slots=True)
class Piste:
    jeu: str
    titre: str
    source: Path
    # Vrai quand le flux doit d'abord sortir d'un paquet ou d'une archive.
    empaquetee: bool
    # Dans une archive EA (HP4) : la clé « <flux>-<n> » et la plage du flux.
    cle: str = ""
    debut: int = 0
    taille: int = 0

    @property
    def identifiant(self) -> str:
        """Ce que la discographie appelle `f` : la clé, sinon le nom du fichier."""
        return self.cle or self.source.stem


def jeux_couverts() -> tuple[str, ...]:
    return tuple(_SOURCES) + tuple(_ARCHIVES)


def titre(nom: str) -> str:
    """« Adv4Greenhouse_Music_edit » → « Adv4Greenhouse ». Brouillon lisible :
    les titres définitifs se relisent à la main avant d'être affichés."""
    mots = [m for m in nom.replace("-", "_").split("_") if m]
    while len(mots) > 1 and mots[-1].lower() in _SUFFIXES:
        mots.pop()
    return " ".join(mots) or nom


def _dossier_musique(dossier_jeu: Path, nom: str) -> Path | None:
    try:
        for enfant in dossier_jeu.iterdir():
            if enfant.is_dir() and enfant.name.lower() == nom:
                return enfant
    except OSError:
        return None
    return None


def pistes(jeu: str, dossier_jeu: Path | None) -> list[Piste]:
    """Les morceaux d'un jeu installé, triés par nom ; vide si rien à lire."""
    if dossier_jeu is not None and jeu in _ARCHIVES:
        if jeu in _A_CONVERTIR and not vgmstream.disponible():
            return []
        archive = dossier_jeu / _ARCHIVES[jeu]
        try:
            st = archive.stat()
        except OSError:
            return []
        return list(_pistes_archive(jeu, archive, st.st_size, st.st_mtime))
    source = _SOURCES.get(jeu)
    if source is None or dossier_jeu is None:
        return []
    dossier = _dossier_musique(dossier_jeu, source[0])
    if dossier is None:
        return []
    try:
        fichiers = sorted(p for p in dossier.glob(source[1]) if p.is_file())
    except OSError:
        return []
    return [Piste(jeu, titre(p.stem), p, p.suffix.lower() == ".umx") for p in fichiers]


@lru_cache(maxsize=4)
def _pistes_archive(jeu: str, archive: Path, _taille: int, _modifie: float) -> tuple[Piste, ...]:
    """Les morceaux d'une `music.big` (0,3 s pour HP4) : gardés tant qu'elle ne change pas."""
    trouvees: list[Piste] = []
    for entree in archives_ea.lister(archive):
        nom = entree.nom.lower()
        # HP4 range aussi des banques (`*_mem0.mus`) ; HP6 nomme son flux `hbpmusic.mus`.
        suffixe = "stream.mus" if jeu == "hp4" else ".mus"
        if not nom.endswith(suffixe) or "sfx" in nom or "amb" in nom:
            continue
        base = Path(entree.nom).stem
        longs = [f for f in archives_ea.flux_schl(archive, entree) if f[1] >= SEUIL_MORCEAU]
        for n, (debut, taille) in enumerate(longs, 1):
            cle = f"{base}-{n}"
            trouvees.append(Piste(jeu, cle, archive, True, cle, debut, taille))
    return tuple(trouvees)


# ─── Paquets Unreal 1 ───

def _compact(d: bytes, i: int) -> tuple[int, int]:
    """Index compact UE1 (signe + 6 bits, puis 7 bits par octet). IndexError hors des données."""
    b = d[i]
    i += 1
    valeur = b & 0x3F
    if b & 0x40:
        decalage = 6
        for _ in range(4):
            c = d[i]
            i += 1
            valeur |= (c & 0x7F) << decalage
            decalage += 7
            if not c & 0x80:
                break
    return (-valeur if b & 0x80 else valeur), i


def _u32(d: bytes, i: int) -> int:
    if i + 4 > len(d):
        raise IndexError(i)
    return int.from_bytes(d[i:i + 4], "little")


def _noms(d: bytes, version: int) -> list[str]:
    nombre, i = _u32(d, 12), _u32(d, 16)
    noms: list[str] = []
    for _ in range(nombre):
        if version >= 64:
            longueur, i = _compact(d, i)
            brut = d[i:i + max(longueur - 1, 0)]
            i += max(longueur, 0)
        else:
            fin = d.index(b"\0", i)
            brut = d[i:fin]
            i = fin + 1
        noms.append(brut.decode("latin-1"))
        i += 4                               # drapeaux du nom
    return noms


def flux_umx(d: bytes) -> tuple[str, bytes] | None:
    """(format, octets) du premier objet `Music` d'un paquet UE1, ou None.

    Disposition relevée sur les paquets de HP1 (version 75) : propriétés vides
    (index de « None »), index du nom de format, int32 de saut, index compact
    du nombre d'octets, puis le flux.
    """
    try:
        if _u32(d, 0) != _MAGIC_UE1:
            return None
        version = int.from_bytes(d[4:6], "little")
        if version < 62:                     # pas de saut avant le tableau paresseux
            return None
        noms = _noms(d, version)
        i = _u32(d, 24)
        for _ in range(_u32(d, 20)):
            _classe, i = _compact(d, i)
            _parent, i = _compact(d, i)
            i += 4
            _nom, i = _compact(d, i)
            i += 4
            taille, i = _compact(d, i)
            if taille <= 0:
                continue
            debut, i = _compact(d, i)
            j = debut
            propriete, j = _compact(d, j)
            if noms[propriete] != "None":    # un objet avec propriétés n'est pas une musique nue
                continue
            index_format, j = _compact(d, j)
            j += 4
            nombre, j = _compact(d, j)
            if nombre <= 0 or j + nombre > len(d):
                continue
            return noms[index_format].lower(), d[j:j + nombre]
    except (IndexError, ValueError):
        return None
    return None


_INTERDITS = '<>:"/\\|?*'


def nom_de_fichier(titre_affiche: str) -> str:
    """Un titre en nom de fichier valable partout (Windows est le plus strict)."""
    propre = "".join("-" if c in _INTERDITS or ord(c) < 32 else c for c in titre_affiche)
    propre = propre.strip().rstrip(". ")
    return propre[:120] or "Morceau"


def exporter(source: Path, titre_affiche: str, dossier: Path) -> Path | None:
    """Copie un morceau lisible dans `dossier` sous son titre, et rend le chemin.

    Demandé par Ludo le 2026-10-24 (« récupérer la musique si les gens la
    veulent ») : le fichier d'origine, sans perte, tiré de la copie du joueur.
    Un fichier du même nom et de la même taille est déjà ce morceau ; un autre
    fichier du même nom n'est jamais écrasé (« Titre (2) »). None si la copie
    échoue.
    """
    base = nom_de_fichier(titre_affiche)
    suffixe = source.suffix.lower()
    try:
        taille = source.stat().st_size
        dossier.mkdir(parents=True, exist_ok=True)
        for n in range(1, 100):
            cible = dossier / (f"{base}{suffixe}" if n == 1 else f"{base} ({n}){suffixe}")
            if not cible.exists():
                break
            if cible.stat().st_size == taille:
                return cible
        else:
            return None
        fd, tmp = tempfile.mkstemp(dir=dossier, suffix=".accio-tmp")
        try:
            with os.fdopen(fd, "wb") as ecrit:
                ecrit.write(source.read_bytes())
            os.replace(tmp, cible)
        except OSError:
            try:
                os.remove(tmp)               # notre propre fichier temporaire
            except OSError:
                pass
            raise
    except OSError as exc:
        log.warning("Phonographe, enregistrement de %s échoué : %s", source, exc)
        return None
    return cible


def _elaguer(dossier: Path, garde: Path) -> None:
    """Retire les WAV les plus anciens du dossier au-delà de `_PLAFOND_WAV` (jamais `garde`)."""
    try:
        wavs = sorted(((f.stat().st_mtime, f.stat().st_size, f) for f in dossier.glob("*.wav")),
                      reverse=True)
        total = 0
        for _date, taille, fichier in wavs:
            total += taille
            if total > _PLAFOND_WAV and fichier != garde:
                fichier.unlink()             # notre propre conversion, refaite à la demande
    except OSError as exc:
        log.debug("Phonographe, élagage de %s : %s", dossier, exc)


def fichier_lisible(piste: Piste, cache: Path) -> Path | None:
    """Le fichier que le lecteur ouvrira : la source, ou le flux sorti du paquet.

    Le flux extrait va dans `<cache>/phonographe/<jeu>/` (écriture atomique),
    et resservira tel quel aux écoutes suivantes.
    """
    if not piste.empaquetee:
        return piste.source if piste.source.is_file() else None
    if piste.taille:
        cible = cache / "phonographe" / piste.jeu / f"{piste.cle}.asf"
        extrait = archives_ea.extraire(piste.source, piste.debut, piste.taille, cible)
        if extrait is None or piste.jeu not in _A_CONVERTIR:
            return extrait
        wav = vgmstream.convertir(extrait, extrait.with_suffix(".wav"))
        if wav is not None:
            try:
                os.utime(wav)                # écouté maintenant : le dernier à partir
            except OSError:
                pass
            _elaguer(wav.parent, wav)
        return wav
    dossier = cache / "phonographe" / piste.jeu
    try:
        existants = list(dossier.glob(piste.source.stem + ".*")) if dossier.is_dir() else []
        if existants:
            return existants[0]
        flux = flux_umx(piste.source.read_bytes())
    except OSError as exc:
        log.debug("Phonographe, %s illisible : %s", piste.source, exc)
        return None
    if flux is None or flux[0] not in _FORMATS_LISIBLES:
        return None
    cible = dossier / f"{piste.source.stem}.{flux[0]}"
    tmp: str | None = None
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dossier, suffix=".accio-tmp")
        with os.fdopen(fd, "wb") as ecrit:
            ecrit.write(flux[1])
        os.replace(tmp, cible)
        tmp = None
    except OSError as exc:
        log.warning("Phonographe, extraction de %s échouée : %s", piste.source, exc)
        return None
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)               # notre propre fichier temporaire
            except OSError:
                pass
    return cible
