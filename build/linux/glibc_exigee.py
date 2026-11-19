"""La glibc la plus récente qu'exige une AppImage, et le refus au-delà d'un plafond.

Lancé par `release.yml` après `build.sh` :

    python build/linux/glibc_exigee.py dist/AccioLauncher-x86_64.AppImage 2.35

Une AppImage démarre seulement sur une machine dont la glibc est au moins
celle de son binaire le plus exigeant. Le build tourne dans un conteneur
Ubuntu 22.04 (glibc 2.35 : Mint 21, Debian 12) ; ce script le PROUVE en
lisant, avec `objdump -T`, les symboles versionnés de chaque fichier ELF de
l'image. Le runtime de type 2 s'extrait sans FUSE (`--appimage-extract`).
"""

import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

_VERSION = re.compile(r"\bGLIBC_(\d+(?:\.\d+)+)\b")


def versions_glibc(sortie_objdump: str) -> set[tuple[int, ...]]:
    """Les versions `GLIBC_x.y` citées par une sortie d'`objdump -T`. Pure."""
    return {tuple(int(n) for n in m.group(1).split(".")) for m in _VERSION.finditer(sortie_objdump)}


def texte(version: tuple[int, ...]) -> str:
    return ".".join(str(n) for n in version)


def trop_recents(exigences: dict[str, set[tuple[int, ...]]],
                 plafond: tuple[int, ...]) -> list[str]:
    """Les fichiers qui exigent plus que `plafond`, avec leur version. Pure."""
    return sorted(f"{nom} : GLIBC_{texte(max(v))}" for nom, v in exigences.items()
                  if v and max(v) > plafond)


def _est_elf(chemin: Path) -> bool:
    try:
        with chemin.open("rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def exigences_du_dossier(racine: Path) -> dict[str, set[tuple[int, ...]]]:
    """Pour chaque ELF sous `racine` : les versions de glibc qu'il réclame."""
    resultat = {}
    fichiers: Iterable[Path] = (p for p in sorted(racine.rglob("*"))
                                if p.is_file() and not p.is_symlink())
    for chemin in fichiers:
        if not _est_elf(chemin):
            continue
        # objdump vient de binutils (installé par le workflow) ; liste d'arguments.
        sortie = subprocess.run(  # nosec B603 B607  # noqa: S603
            ["objdump", "-T", str(chemin)], capture_output=True,  # noqa: S607
            encoding="utf-8", errors="replace", check=False).stdout
        resultat[str(chemin.relative_to(racine))] = versions_glibc(sortie)
    return resultat


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage : glibc_exigee.py <AppImage> <plafond, ex. 2.35>")
        return 2
    image = Path(argv[0]).resolve()
    plafond = tuple(int(n) for n in argv[1].split("."))
    with tempfile.TemporaryDirectory() as dossier:
        # L'image vient de NOTRE build ; liste d'arguments, aucun shell.
        code = subprocess.run(  # nosec B603  # noqa: S603
            [str(image), "--appimage-extract"], cwd=dossier,
            capture_output=True, check=False).returncode
        racine = Path(dossier) / "squashfs-root"
        if code != 0 or not racine.is_dir():
            print(f"ERREUR : extraction de {image.name} échouée (code {code}).")
            return 1
        exigences = exigences_du_dossier(racine)
    toutes = set().union(*exigences.values()) if exigences else set()
    if not toutes:
        print("ERREUR : aucun symbole GLIBC lu : objdump absent ou image vide.")
        return 1
    print(f"{len(exigences)} fichiers ELF, glibc exigée : {texte(max(toutes))} "
          f"(plafond {texte(plafond)})")
    fautifs = trop_recents(exigences, plafond)
    if fautifs:
        print("ERREUR : binaires trop exigeants :")
        print("\n".join(f"  - {f}" for f in fautifs))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
