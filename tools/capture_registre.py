r"""Capture et compare des entrees de registre — pour trouver la cle d'un jeu.

Pourquoi cet outil
==================
HP7 partie 1 lit sa LANGUE dans le registre. On ne peut ni deviner le nom de la
valeur, ni son type, ni ce qu'elle accepte ("French" ? "FR" ? 1036 ?) : seul le
jeu le sait. Le seul moyen fiable est de le lui faire ecrire, puis de regarder.

Mode d'emploi
=============
    1. Lancer le jeu, choisir le FRANCAIS, quitter.
       python tools/capture_registre.py capture avant.json

    2. Relancer, choisir l'ANGLAIS, quitter.
       python tools/capture_registre.py capture apres.json

    3. python tools/capture_registre.py diff avant.json apres.json

La difference donne exactement : la ruche, le chemin de la cle, le NOM de la
valeur, son TYPE, et les deux valeurs. C'est tout ce qu'il manque pour finir
`post_install.apply_registry` (valeurs nommees, REG_DWORD, vue 32 bits).

Options
=======
    --motif potter        mot-cle cherche dans les chemins (defaut : potter)
    --cle "Software\..."  capture UNE cle precise au lieu de chercher

Les deux vues 32 et 64 bits sont lues : Python est 64 bits, un jeu 32 bits ecrit
dans WOW6432Node, et ne lire qu'une vue laisserait passer la moitie du registre.
"""

import argparse
import json
import sys
from pathlib import Path

if sys.platform != "win32":
    print("Cet outil n'a de sens que sous Windows.")
    sys.exit(1)

import winreg

RUCHES = (("HKCU", winreg.HKEY_CURRENT_USER), ("HKLM", winreg.HKEY_LOCAL_MACHINE))
VUES = (("32", winreg.KEY_WOW64_32KEY), ("64", winreg.KEY_WOW64_64KEY))
RACINES = ("Software",)
PROFONDEUR_MAX = 6

# Table EXPLICITE, surtout pas construite par balayage de dir(winreg) : le
# module y melange les constantes de TYPE et celles d'OPTION, qui partagent les
# memes valeurs numeriques. Un REG_SZ (1) ressortait en REG_WHOLE_HIVE_VOLATILE
# et un REG_DWORD (4) en REG_OPTION_BACKUP_RESTORE — de quoi ecrire le mauvais
# type dans le registre d'un utilisateur en croyant recopier le bon.
_TYPES = {
    winreg.REG_NONE: "REG_NONE",
    winreg.REG_SZ: "REG_SZ",
    winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ",
    winreg.REG_BINARY: "REG_BINARY",
    winreg.REG_DWORD: "REG_DWORD",
    winreg.REG_DWORD_BIG_ENDIAN: "REG_DWORD_BIG_ENDIAN",
    winreg.REG_LINK: "REG_LINK",
    winreg.REG_MULTI_SZ: "REG_MULTI_SZ",
    winreg.REG_RESOURCE_LIST: "REG_RESOURCE_LIST",
    winreg.REG_FULL_RESOURCE_DESCRIPTOR: "REG_FULL_RESOURCE_DESCRIPTOR",
    winreg.REG_RESOURCE_REQUIREMENTS_LIST: "REG_RESOURCE_REQUIREMENTS_LIST",
    winreg.REG_QWORD: "REG_QWORD",
}


def _valeurs(cle) -> dict:
    """Toutes les valeurs NOMMEES d'une cle, avec leur type."""
    out = {}
    i = 0
    while True:
        try:
            nom, donnee, type_ = winreg.EnumValue(cle, i)
        except OSError:
            break
        out[nom or "(par defaut)"] = {
            "type": _TYPES.get(type_, str(type_)),
            "valeur": donnee if isinstance(donnee, (str, int)) else repr(donnee),
        }
        i += 1
    return out


def _parcours(ruche, hkey, vue_nom, acces, chemin, motif, profondeur, sortie):
    try:
        cle = winreg.OpenKey(hkey, chemin, 0, winreg.KEY_READ | acces)
    except OSError:
        return
    with cle:
        if motif in chemin.lower():
            vals = _valeurs(cle)
            if vals:
                sortie[r"%s[%s]\%s" % (ruche, vue_nom, chemin)] = vals
        if profondeur >= PROFONDEUR_MAX:
            return
        i = 0
        while True:
            try:
                sous = winreg.EnumKey(cle, i)
            except OSError:
                break
            i += 1
            _parcours(ruche, hkey, vue_nom, acces, chemin + "\\" + sous,
                      motif, profondeur + 1, sortie)


def capture(motif: str, cle_precise: str | None) -> dict:
    sortie: dict = {}
    for ruche, hkey in RUCHES:
        for vue_nom, acces in VUES:
            if cle_precise:
                try:
                    with winreg.OpenKey(hkey, cle_precise, 0,
                                        winreg.KEY_READ | acces) as c:
                        vals = _valeurs(c)
                        if vals:
                            sortie[r"%s[%s]\%s" % (ruche, vue_nom, cle_precise)] = vals
                except OSError:
                    pass
            else:
                for racine in RACINES:
                    _parcours(ruche, hkey, vue_nom, acces, racine,
                              motif.lower(), 0, sortie)
    return sortie


def diff(avant: dict, apres: dict) -> int:
    cles = sorted(set(avant) | set(apres))
    change = 0
    for cle in cles:
        a, b = avant.get(cle, {}), apres.get(cle, {})
        for nom in sorted(set(a) | set(b)):
            va, vb = a.get(nom), b.get(nom)
            if va == vb:
                continue
            change += 1
            print("  %s" % cle)
            print("      valeur  : %r" % nom)
            print("      type    : %s" % ((vb or va)["type"]))
            print("      avant   : %r" % (va["valeur"] if va else "(absente)"))
            print("      apres   : %r" % (vb["valeur"] if vb else "(absente)"))
            print()
    if not change:
        print("  Aucune difference. Le jeu n'a peut-etre rien reecrit, ou la cle")
        print("  est hors du motif cherche : reessayer avec --motif ou --cle.")
    else:
        print("  %d valeur(s) modifiee(s)." % change)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sous = ap.add_subparsers(dest="action", required=True)
    c = sous.add_parser("capture", help="enregistre un instantane")
    c.add_argument("fichier")
    c.add_argument("--motif", default="potter")
    c.add_argument("--cle", default=None)
    d = sous.add_parser("diff", help="compare deux instantanes")
    d.add_argument("avant")
    d.add_argument("apres")
    args = ap.parse_args()

    if args.action == "capture":
        data = capture(args.motif, args.cle)
        Path(args.fichier).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("%d cle(s) avec des valeurs -> %s" % (len(data), args.fichier))
        for cle in list(data)[:20]:
            print("   ", cle)
        if not data:
            print("Rien trouve. Essayer --motif ea, --motif warner, ou --cle.")
        return 0

    avant = json.loads(Path(args.avant).read_text(encoding="utf-8"))
    apres = json.loads(Path(args.apres).read_text(encoding="utf-8"))
    return diff(avant, apres)


if __name__ == "__main__":
    sys.exit(main())
