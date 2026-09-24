r"""Vérifie, sur une vraie machine Linux, ce que la suite de tests ne peut pas.

La suite de tests ne lance jamais Wine : elle remplace le lanceur par un faux,
et le registre par des fichiers qu'elle pose elle-même. C'est voulu (un test ne
doit pas dépendre de la machine), mais ça laisse une question ouverte : sur
CETTE machine, avec SON umu ou SON wine, est-ce que ça marche ?

Mode d'emploi (depuis le dossier des sources, ou n'importe où avec le chemin) :

    python3 tools/verifier_wine.py              # relevé, sans rien écrire
    python3 tools/verifier_wine.py --preparer   # crée le préfixe + composants
    python3 tools/verifier_wine.py --registre   # aller-retour dans le registre

Le relevé seul ne modifie rien. `--preparer` fait ce que ferait le launcher au
premier lancement d'un jeu (winetricks télécharge chez Microsoft, umu peut
télécharger Proton). `--registre` écrit UNE valeur d'essai sous
`HKCU\Software\AccioLauncher\Verification` du préfixe — jamais une clé de jeu —
puis la relit : c'est le chemin exact que suit l'écriture de la langue de HP7.

`--prefixe DOSSIER` travaille sur un autre préfixe que celui du launcher.
Rien n'est envoyé nulle part : tout s'affiche ici.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import compat, game_registry, system_checks  # noqa: E402
from src.core.preparation_wine import PreparationWine  # noqa: E402

CLE_ESSAI = r"Software\AccioLauncher\Verification"


def _titre(texte: str) -> None:
    print(f"\n── {texte} " + "─" * max(0, 60 - len(texte)))


def releve(pfx: Path) -> int:
    lanceur = compat.lanceur()
    _titre("Lanceur de compatibilité")
    if lanceur is None:
        print("AUCUN : ni umu-run ni wine trouvés. Sur Bazzite : ujust update.")
        return 1
    print(f"famille    : {lanceur.famille}")
    print(f"exécutable : {lanceur.executable}")
    if lanceur.famille == "umu":
        print(f"Proton     : {lanceur.proton or '(choisi par umu : UMU-Proton)'}")
    else:
        print(f"winetricks : {lanceur.winetricks or 'INTROUVABLE'}")

    _titre("Préfixe")
    print(f"dossier    : {pfx}")
    print(f"prêt       : {'oui' if compat.pret(pfx) else 'NON (lancez --preparer)'}")
    if compat.pret(pfx):
        print(f"arch       : {compat.architecture(pfx)}")
        print(f"page ANSI  : {compat.encodage_ansi(pfx)}")
        print(f"Documents  : {compat.documents(pfx)}")
        print(f"   vu du jeu : {compat.chemin_windows(compat.documents(pfx), pfx)}")
        print(f"AppData    : {compat.appdata_local(pfx)}")
        print(f"winetricks : {', '.join(sorted(compat.verbes_installes(pfx))) or '(rien)'}")

    _titre("Composants (ce que vérifie le lancement)")
    system_checks.invalidate_vcredist_cache()
    for nom, (test, _) in system_checks.PREREQUIS.items():
        print(f"{nom:18} : {'présent' if test() else 'MANQUANT'}")
    print(f"registre disponible : {'oui' if game_registry.disponible() else 'non'}")
    return 0


def preparer(pfx: Path) -> int:
    lanceur = compat.lanceur()
    if lanceur is None:
        print("Aucun lanceur : rien à préparer.")
        return 1
    system_checks.invalidate_vcredist_cache()
    manquants = system_checks.prerequis_manquants(tuple(system_checks.PREREQUIS))
    verbes = [system_checks.VERBES_WINETRICKS[m] for m in manquants]
    journal = compat.dossier_journaux() / "wine-preparation.log"
    _titre("Préparation")
    print(f"verbes : {' '.join(verbes) or '(aucun)'} — journal : {journal}")
    fil = PreparationWine(lanceur, pfx, verbes, journal)
    fil.etape.connect(lambda e, v: print(f"… {e} {v}"))
    fin = []
    fil.preparation_terminee.connect(lambda ok, raison: fin.append((ok, raison)))
    debut = time.monotonic()
    fil.run()                    # dans ce processus : c'est un outil, pas l'interface
    ok, raison = fin[0]
    print(f"résultat : {'réussie' if ok else 'ÉCHEC ' + raison} en {time.monotonic() - debut:.0f} s")
    return 0 if ok else 1


def registre() -> int:
    _titre("Aller-retour dans le registre du préfixe")
    if not game_registry.disponible():
        print("Registre indisponible : préfixe pas prêt, ou pas de lanceur.")
        return 1
    valeur = time.strftime("essai %Y-%m-%d %H:%M:%S")
    print(f"écrit  : HKCU\\{CLE_ESSAI} « Test » = {valeur!r}")
    debut = time.monotonic()
    ok = game_registry.ecrire_valeurs("HKCU", CLE_ESSAI, {"Test": valeur}, vue=64)
    print(f"relu   : {game_registry.lire_valeurs('HKCU', CLE_ESSAI, ['Test'], 64)}")
    print(f"résultat : {'OK' if ok else 'ÉCHEC'} en {time.monotonic() - debut:.1f} s")
    return 0 if ok else 1


def main() -> int:
    if sys.platform == "win32":
        print("Sous Windows, les jeux se lancent sans Wine : rien à vérifier ici.")
        return 1
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--preparer", action="store_true")
    parser.add_argument("--registre", action="store_true")
    parser.add_argument("--prefixe", type=Path)
    args = parser.parse_args()
    if args.prefixe is not None:
        choisi = args.prefixe.expanduser().resolve()
        compat.prefixe = lambda famille=None: choisi
    pfx = compat.prefixe()
    code = 0
    if args.preparer:
        code |= preparer(pfx)
    code |= releve(pfx)
    if args.registre:
        code |= registre()
    return code


if __name__ == "__main__":
    sys.exit(main())
