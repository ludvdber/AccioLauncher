"""Banc de RAPIDITÉ du launcher : démarrage, réponse, blocages, images, mémoire, disque, processeur.

Pourquoi ce banc
================
Les mesures de rapidité de ce dépôt étaient faites à la main, une par une, au
moment d'un chantier (fond sur la carte graphique, imports paresseux…), puis
perdues : rien ne disait si le chantier suivant les avait défaites. Ce banc les
rejoue toutes d'une commande, sur le VRAI démarrage (`main.main`) et un parcours
complet de joueur, et sort un tableau (Markdown + JSON) où chaque budget porte
sa cible à côté.

Ce qu'il mesure
---------------
  * Démarrage : du lancement du processus au premier paint de la fenêtre, puis
    à la boucle d'événements LIBRE (cinq battements à l'heure d'affilée). À
    chaud : un tour d'échauffement jeté, puis la médiane de N tours.
    `--froid` : un seul tour, à lancer JUSTE APRÈS UN REDÉMARRAGE de Windows ;
    le banc ne vide jamais le cache du système lui-même (ce serait toucher au
    système).
  * Réponse : pour chaque action du parcours (changer de jeu, revenir à la
    fiche, engrenage et ses rubriques, Paramètres et leurs rubriques, Carnet,
    jeux et sauvegardes du folio, chaque Collection, une fiche de
    l'Encyclopédie, la bande-annonce), le temps entre l'événement (un vrai clic
    QTest) et la fin du travail du fil d'interface : le dernier paint traité
    avant le premier battement revenu à l'heure.
  * Blocages du fil d'interface > 50 ms : un battement (QTimer 5 ms) sur le
    fil principal, un fil-sentinelle qui le surveille et, pendant un blocage,
    échantillonne la pile Python du fil principal (`sys._current_frames`) :
    c'est elle qui donne les CAUSES (fichier:ligne).
  * Images : durée de traitement de chaque `UpdateRequest` de la fenêtre et
    écart entre deux images, pendant les changements de jeu et les
    défilements. En vraie fenêtre, `QSG_RENDER_TIMING=1` ajoute les temps des
    scènes Qt Quick (lignes `qt.scenegraph.time.*`).
  * Mémoire : octets privés (Windows) ou RSS, au repos, au pic et en régime
    pour chaque page ouverte, et après sa fermeture (ce qui reste gardé).
  * Disque : lectures PAR FICHIER (crochet d'audit `open` pour Python ;
    QPixmap, QImage, QImageReader, QIcon, QFile, QMovie et
    `QFontDatabase.addApplicationFont` enveloppés pour Qt), avec la liste des
    fichiers lus plus d'une fois et leur taille ; total des octets lus par le
    processus (compteurs du système) pour ce qui échappe au comptage.
  * Processeur : part d'un cœur au repos (10 s), pendant une bande-annonce,
    pendant un défilement.
  * Profilage cProfile (sauf `--sans-profilage`) du démarrage et du
    changement de sauvegarde du folio, dans un processus à part pour ne pas
    fausser les autres mesures.

Profils
-------
  * `--profil ludo` : la machine telle quelle.
  * `--profil vieux-pc` : rendu Qt Quick logiciel (`--carte software`,
    QT_QUICK_BACKEND=software, défaut) ou carte graphique logicielle WARP
    (`--carte warp` : QSG_RHI_BACKEND=d3d11 + QSG_RHI_PREFER_SOFTWARE_RENDERER=1,
    noms vérifiés dans Qt6Quick.dll 6.11) ; deux cœurs (affinité) ; plafond de
    4 Go de mémoire privée par un objet job Windows (ctypes). Sous Linux :
    affinité par `os.sched_setaffinity`, Mesa logiciel (LIBGL_ALWAYS_SOFTWARE),
    et le plafond n'est que MESURÉ (RLIMIT_AS compterait la mémoire virtuelle).

Modes
-----
  * `--hors-ecran` (défaut) : QT_QPA_PLATFORM=offscreen. Ne vaut que pour la
    LOGIQUE : l'affichage (composition, carte graphique) y est sous-estimé, le
    tableau le dit en tête.
  * `--vraie-fenetre` : plateforme native, la fenêtre S'AFFICHE. Seulement
    quand personne n'utilise le PC.

Isolement
---------
Rien n'est écrit chez le joueur : le dossier personnel du processus mesuré
(HOME, USERPROFILE) est un dossier du banc, avec une COPIE de `_Launcher`
(config, catalogue, journaux de parties, bandes-annonces, caches), une copie
des sauvegardes (Documents et AppData\\Local) et une copie partielle des jeux
(fichiers de 64 Mo au plus copiés, les plus gros remplacés par des fichiers
vides du même nom ; `--jeux-copie` en réutilise une). La config copiée porte
son_coupe=True, musique_fond="", Discord, manette et copies de sauvegardes
coupés. Un crochet d'audit REFUSE toute écriture Python hors du banc et toute
connexion réseau ; la vérification des mises à jour et le rattrapage des
bandes-annonces sont neutralisés. Les captures d'écran (Images\\Accio Launcher)
sont lues en place, jamais écrites.

Usage :
    py -3.15 tools/banc_rapidite.py
    py -3.15 tools/banc_rapidite.py --profil vieux-pc --etiquette avant_vieux_pc
    py -3.15 tools/banc_rapidite.py --froid
    py -3.15 tools/banc_rapidite.py --vraie-fenetre
Sortie : <sortie>/<etiquette>.json et .md ; profils dans <sortie>/<etiquette>_profils/.
"""

import argparse
import json
import logging
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

_LOG = logging.getLogger("banc_rapidite")

DEPOT = Path(__file__).resolve().parent.parent
_AUDIT = Path(tempfile.gettempdir()) / "claude" / "afcb9cc43e06cd62" / \
    "e4ac7a1e-1366-4409-baa6-3b3067ec483a" / "scratchpad" / "audit"
SORTIE_DEFAUT = _AUDIT / "rapidite" if _AUDIT.is_dir() else Path(tempfile.gettempdir()) / "accio_banc_rapidite"
JEUX_REELS = Path.home() / "Games" / "AccioLauncher"
SEUIL_COPIE_MO = 64

# Les cibles, en un seul endroit : le tableau les montre à côté de chaque valeur.
CIBLES = {
    "demarrage_chaud_ms": 1000.0,
    "demarrage_froid_ms": 3000.0,
    "clic_ms": 100.0,
    "rubrique_ms": 50.0,
    "blocage_ms": 50.0,
    "image_p95_ms": 40.0,      # le Ticker bat à 33 ms (30 images/s)
    "image_max_ms": 50.0,
    "memoire_plafond_mo": 4096.0,
    "memoire_garde_mo": 20.0,
    "cpu_repos_pct": 5.0,
    "cpu_bande_annonce_pct": 20.0,
    "cpu_defilement_pct": 60.0,
    "fichiers_relus": 0.0,
}
# Catégories d'action : celles qui changent ce qu'on voit sans ouvrir de page.
_RAPIDES = ("jeu", "rubrique", "sauvegarde")
AVERTISSEMENT_HORS_ECRAN = (
    "Mode HORS ÉCRAN (QT_QPA_PLATFORM=offscreen) : ces chiffres valent pour la LOGIQUE "
    "du fil d'interface. L'affichage réel (composition, carte graphique, synchronisation "
    "verticale) y est SOUS-ESTIMÉ ; seule `--vraie-fenetre` le tranche.")
_MODULES = (".py", ".pyc", ".pyd", ".dll", ".so")


# ════════════════════════════ Rendu du tableau (pur, sans Qt) ════════════════════════════

def _fmt(valeur, unite: str = "ms") -> str:
    if valeur is None:
        return "—"
    if isinstance(valeur, float):
        return f"{valeur:.1f} {unite}".strip()
    return f"{valeur} {unite}".strip()


def _ligne(budget: str, profil: str, valeur, cible: str, ok: bool | None, detail: str = "",
           unite: str = "ms") -> dict:
    return {"budget": budget, "profil": profil, "valeur": _fmt(valeur, unite) if not isinstance(valeur, str)
            else valeur, "cible": cible, "ok": ok, "detail": detail}


def _sous(valeur, cible) -> bool | None:
    return None if valeur is None else valeur < cible


def _p(valeurs: list[float], q: float) -> float | None:
    if not valeurs:
        return None
    rangees = sorted(valeurs)
    k = min(len(rangees) - 1, max(0, round(q * (len(rangees) - 1))))
    return rangees[k]


def stats_images(sessions: list) -> dict:
    """Écarts et durées de peinture d'images [(début, fin)] en secondes, par SESSION (une animation,
    un défilement) : l'écart entre deux sessions n'est pas une image lente. Une liste plate de
    paires vaut une seule session."""
    if sessions and sessions[0] and isinstance(sessions[0][0], (int, float)):
        sessions = [sessions]
    ecarts: list[float] = []
    durees: list[float] = []
    n = 0
    for images in sessions:
        debuts = [a for a, _ in images]
        ecarts += [(b - a) * 1000 for a, b in zip(debuts, debuts[1:], strict=False)]
        durees += [(b - a) * 1000 for a, b in images]
        n += len(images)
    return {"images": n, "sessions": len(sessions),
            "ecart_p50_ms": _p(ecarts, 0.5), "ecart_p95_ms": _p(ecarts, 0.95),
            "ecart_max_ms": max(ecarts) if ecarts else None,
            "peinture_p50_ms": _p(durees, 0.5), "peinture_p95_ms": _p(durees, 0.95),
            "peinture_max_ms": max(durees) if durees else None,
            "lentes_33ms": sum(1 for e in ecarts if e > 33.4)}


def lignes_tableau(res: dict) -> list[dict]:
    """Une ligne par budget, cible à côté. `res` : le JSON produit par le banc."""
    profil = res.get("meta", {}).get("profil", "?")
    lignes: list[dict] = []
    dem = res.get("demarrage") or {}
    froid = bool(dem.get("froid"))
    cible = CIBLES["demarrage_froid_ms" if froid else "demarrage_chaud_ms"]
    util, paint = dem.get("mediane_utilisable_ms"), dem.get("mediane_premier_paint_ms")
    lignes.append(_ligne(f"Démarrage {'à froid' if froid else 'à chaud'} : fenêtre utilisable", profil, util,
                         f"< {cible:.0f} ms", _sous(util, cible),
                         f"premier paint {_fmt(paint)} ; {len(dem.get('tours', []))} tour(s) mesuré(s)"))
    actions = res.get("actions") or []
    for cat, cle, nom in (("rapides", "rubrique_ms", "changement de jeu, rubrique, sauvegarde"),
                          ("clics", "clic_ms", "tout autre clic")):
        choix = [a for a in actions if (a.get("categorie") in _RAPIDES) == (cat == "rapides")]
        valeurs = [a["reponse_ms"] for a in choix if a.get("reponse_ms") is not None]
        if not choix:
            continue
        pire = max(choix, key=lambda a: a.get("reponse_ms") or -1)
        hors = [a for a in choix if a.get("reponse_ms") is not None and a["reponse_ms"] >= CIBLES[cle]]
        lignes.append(_ligne(f"Réponse, pire cas ({nom})", profil, pire.get("reponse_ms"),
                             f"< {CIBLES[cle]:.0f} ms", _sous(pire.get("reponse_ms"), CIBLES[cle]),
                             f"« {pire.get('nom')} » ; médiane {_fmt(_p(valeurs, 0.5))} ; "
                             f"{len(hors)} sur {len(choix)} hors cible"))
    blocs = res.get("blocages") or []
    total = sum(b["duree_ms"] for b in blocs)
    pire_b = max(blocs, key=lambda b: b["duree_ms"]) if blocs else None
    lignes.append(_ligne("Blocages du fil d'interface > 50 ms (parcours)", profil, f"{len(blocs)}",
                         "0", not blocs,
                         f"total {total:.0f} ms ; pire {pire_b['duree_ms']:.0f} ms pendant « {pire_b['etape']} » "
                         f"({pire_b['cause']})" if pire_b else ""))
    hors_3d = [b for b in blocs if not any(m in b["etape"].lower() for m in ("personnages", "bestiaire"))]
    if len(hors_3d) != len(blocs):
        pire_h = max(hors_3d, key=lambda b: b["duree_ms"]) if hors_3d else None
        lignes.append(_ligne("Blocages > 50 ms hors Personnages et Bestiaire (modèles 3D)", profil,
                             f"{len(hors_3d)}", "0", not hors_3d,
                             f"total {sum(b['duree_ms'] for b in hors_3d):.0f} ms ; pire {pire_h['duree_ms']:.0f} ms "
                             f"pendant « {pire_h['etape']} » ({pire_h['cause']})" if pire_h else ""))
    for nom, st in (res.get("animations") or {}).items():
        p95 = st.get("ecart_p95_ms")
        ok = None if p95 is None else (p95 <= CIBLES["image_p95_ms"]
                                       and (st.get("ecart_max_ms") or 0) <= CIBLES["image_max_ms"])
        lignes.append(_ligne(f"Images : {nom}", profil, p95,
                             f"écart p95 ≤ {CIBLES['image_p95_ms']:.0f} ms, max ≤ {CIBLES['image_max_ms']:.0f}",
                             ok, f"{st.get('images')} images ; max {_fmt(st.get('ecart_max_ms'))} ; "
                             f"peinture p95 {_fmt(st.get('peinture_p95_ms'))} ; "
                             f"{st.get('lentes_33ms')} écarts > 33 ms"))
    for quick, st in (res.get("quick") or {}).items():
        lignes.append(_ligne(f"Scène Qt Quick : {quick}", profil, st.get("p95_ms"), "≤ 16.7 ms",
                             _sous(st.get("p95_ms"), 16.7), f"{st.get('n')} mesures"))
    mem = res.get("memoire") or {}
    pic = mem.get("pic_mo")
    lignes.append(_ligne("Mémoire : pic du parcours", profil, pic, f"< {CIBLES['memoire_plafond_mo']:.0f} Mo",
                         _sous(pic, CIBLES["memoire_plafond_mo"]),
                         f"au repos {_fmt(mem.get('repos_mo'), 'Mo')} ; {mem.get('mesure', '')}", "Mo"))
    for page in mem.get("pages", []):
        garde = page.get("garde_mo")
        lignes.append(_ligne(f"Mémoire : {page['page']} (gardé après fermeture)", profil, garde,
                             f"< {CIBLES['memoire_garde_mo']:.0f} Mo", _sous(garde, CIBLES["memoire_garde_mo"]),
                             f"avant {_fmt(page.get('avant_mo'), 'Mo')}, pic {_fmt(page.get('pic_mo'), 'Mo')}, "
                             f"ouverte {_fmt(page.get('ouverte_mo'), 'Mo')}", "Mo"))
    disque = res.get("disque") or {}
    relus = disque.get("relus") or []
    lignes.append(_ligne("Disque : fichiers lus plus d'une fois", profil, f"{len(relus)}", "0", not relus,
                         ", ".join(f"{Path(r['fichier']).name} ×{r['lectures']}" for r in relus[:6])))
    for cpu in res.get("processeur") or []:
        cle = {"repos": "cpu_repos_pct", "bande-annonce": "cpu_bande_annonce_pct"}.get(
            cpu["situation"], "cpu_defilement_pct")
        lignes.append(_ligne(f"Processeur : {cpu['situation']}", profil, cpu.get("part_coeur_pct"),
                             f"≤ {CIBLES[cle]:.0f} % d'un cœur", None if cpu.get("part_coeur_pct") is None
                             else cpu["part_coeur_pct"] <= CIBLES[cle],
                             f"{cpu.get('duree_s', 0):.0f} s{' ; ' + cpu['note'] if cpu.get('note') else ''}", "%"))
    return lignes


def _table(entetes: list[str], rangs: list[list[str]]) -> list[str]:
    def propre(c) -> str:
        return str(c).replace("|", "\\|").replace("\n", " ")
    sortie = ["| " + " | ".join(entetes) + " |", "|" + "|".join("---" for _ in entetes) + "|"]
    sortie += ["| " + " | ".join(propre(c) for c in r) + " |" for r in rangs]
    return sortie


def rendre_markdown(res: dict) -> str:
    """Le rapport lisible : en-tête, tableau des budgets, puis le détail."""
    meta = res.get("meta", {})
    md = [f"# Banc de rapidité — {meta.get('etiquette', '')}", ""]
    if meta.get("mode", "hors-ecran") == "hors-ecran":
        md += [f"> **{AVERTISSEMENT_HORS_ECRAN}**", ""]
    md.append(f"Profil **{meta.get('profil', '?')}**, mode {meta.get('mode', '?')}, "
              f"{meta.get('date', '')}, commit {meta.get('commit', '?')}, Python {meta.get('python', '?')}, "
              f"Qt {meta.get('qt', '?')}.")
    for cle in ("rendu", "affinite", "plafond_memoire", "jeux_copie"):
        if meta.get(cle):
            md.append(f"- {cle.replace('_', ' ')} : {meta[cle]}")
    md.append("")
    md += _table(["Budget", "Valeur", "Cible", "OK", "Détail"],
                 [[ligne["budget"], ligne["valeur"], ligne["cible"],
                   {True: "oui", False: "**NON**", None: "—"}[ligne["ok"]], ligne["detail"]]
                  for ligne in lignes_tableau(res)])
    actions = res.get("actions") or []
    if actions:
        md += ["", "## Réponse par action", ""]
        md += _table(["Action", "Catégorie", "Réponse", "Cible", "Appel", "Calme", "Lectures", "Octets lus",
                      "Fichiers lus (extrait)"],
                     [[a["nom"], a["categorie"], _fmt(a.get("reponse_ms")),
                       f"< {CIBLES['rubrique_ms' if a['categorie'] in _RAPIDES else 'clic_ms']:.0f}",
                       _fmt(a.get("appel_ms")), _fmt(a.get("calme_ms")), str(a.get("lectures", 0)),
                       f"{(a.get('octets_lus') or 0) / 1e6:.1f} Mo", ", ".join(a.get("fichiers", [])[:3])]
                      for a in actions])
    blocs = res.get("blocages") or []
    if blocs:
        md += ["", "## Blocages du fil d'interface (> 50 ms)", ""]
        md += _table(["Étape", "Durée", "Cause (cadre du dépôt le plus profond)", "Appel commun", "Pile"],
                     [[b["etape"], _fmt(b["duree_ms"]), b["cause"], b.get("appel", ""),
                       " ← ".join(b.get("pile", [])[:5])]
                      for b in sorted(blocs, key=lambda b: -b["duree_ms"])[:40]])
        causes = res.get("causes") or []
        if causes:
            md += ["", "### Causes cumulées", ""]
            md += _table(["Cause", "Blocages", "Total"],
                         [[c["cause"], str(c["n"]), _fmt(c["total_ms"])] for c in causes[:25]])
    mem = res.get("memoire") or {}
    if mem.get("pages"):
        md += ["", "## Mémoire par page", "", f"Mesure : {mem.get('mesure', '')}.", ""]
        md += _table(["Page", "Avant", "Pic", "Ouverte", "Après fermeture", "Gardé"],
                     [[p["page"], _fmt(p.get("avant_mo"), "Mo"), _fmt(p.get("pic_mo"), "Mo"),
                       _fmt(p.get("ouverte_mo"), "Mo"), _fmt(p.get("apres_mo"), "Mo"),
                       _fmt(p.get("garde_mo"), "Mo")] for p in mem["pages"]])
    disque = res.get("disque") or {}
    if disque:
        md += ["", "## Disque", "",
               f"Fichiers lus : {disque.get('fichiers', 0)} ; lectures : {disque.get('lectures', 0)} ; "
               f"modules Python et bibliothèques : {disque.get('modules', 0)} ouvertures (hors tableau) ; "
               f"octets lus par le processus : {(disque.get('octets_processus') or 0) / 1e6:.1f} Mo.", ""]
        if disque.get("relus"):
            md += _table(["Fichier", "Lectures", "Taille", "Origine", "Phases"],
                         [[r["fichier"], str(r["lectures"]), f"{(r.get('taille') or 0) / 1e3:.1f} Ko",
                           r.get("origine", ""), ", ".join(r.get("phases", []))] for r in disque["relus"][:60]])
        if disque.get("echappe"):
            md += ["", "Ce qui échappe au comptage par fichier : " + " ; ".join(disque["echappe"]) + "."]
    cpu = res.get("processeur") or []
    if cpu:
        md += ["", "## Processeur", ""]
        md += _table(["Situation", "Part d'un cœur", "Durée", "Note"],
                     [[c["situation"], _fmt(c.get("part_coeur_pct"), "%"), _fmt(c.get("duree_s"), "s"),
                       c.get("note", "")] for c in cpu])
    if res.get("profils"):
        md += ["", "## Profilage (cProfile)", ""]
        for nom, chemin in res["profils"].items():
            md.append(f"- {nom} : `{chemin}`")
    if res.get("erreurs"):
        md += ["", "## Erreurs du banc", ""] + [f"- {e}" for e in res["erreurs"]]
    if res.get("limites"):
        md += ["", "## Limites", ""] + [f"- {lim}" for lim in res["limites"]]
    return "\n".join(md) + "\n"


# ════════════════════════════ Isolement (processus parent) ════════════════════════════

def copier_jeux_partiels(source: Path, cible: Path, seuil_mo: int = SEUIL_COPIE_MO) -> dict:
    """Copie les jeux : fichiers de `seuil_mo` au plus copiés, les plus gros remplacés par des
    fichiers VIDES du même nom (une présence, pas un contenu). Jamais de lien dur : la copie
    pourrait être écrite. Reprend une copie interrompue (même taille et même date : sauté)."""
    seuil = seuil_mo * 1024 * 1024
    bilan = {"copies": 0, "vides": 0, "octets": 0}
    for dossier in sorted(p for p in source.iterdir() if p.is_dir() and p.name != "_Launcher"):
        for chemin in dossier.rglob("*"):
            if not chemin.is_file():
                continue
            dest = cible / chemin.relative_to(source)
            infos = chemin.stat()
            if infos.st_size > seuil:
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(b"")
                bilan["vides"] += 1
                continue
            if dest.exists() and dest.stat().st_size == infos.st_size \
                    and int(dest.stat().st_mtime) == int(infos.st_mtime):
                bilan["copies"] += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(chemin, dest)
            bilan["copies"] += 1
            bilan["octets"] += infos.st_size
    (cible / ".banc_complet").write_text(json.dumps(bilan), encoding="utf-8")
    return bilan


def _trouver_jeux_copie(demande: str | None, sortie: Path) -> Path | None:
    """La copie à réutiliser : d'abord une copie que ce banc a FINIE (marque `.banc_complet`), puis
    celle d'un autre banc d'audit si elle existe ; aucune : le banc fait la sienne."""
    if demande:
        return Path(demande)
    candidats = (sortie / "jeux_copie", sortie.parent / "banc" / "jeux_copie")
    for candidat in candidats:
        if (candidat / ".banc_complet").exists():
            return candidat
    for candidat in candidats:
        if candidat.is_dir() and any(p.is_dir() and p.name.upper().startswith("HP") for p in candidat.iterdir()):
            return candidat
    return None


def _copier_arbre(source: Path, cible: Path, sauf: tuple[str, ...] = ()) -> None:
    if not source.exists():
        return
    if source.is_file():
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, cible)
        return
    shutil.copytree(source, cible, dirs_exist_ok=True,
                    ignore=lambda _d, noms: [n for n in noms if n in sauf])


def _dossiers_sauvegardes() -> list[tuple[str, Path]]:
    """Les dossiers de sauvegardes que le catalogue désigne, chez le joueur (lecture seule)."""
    sys.path.insert(0, str(DEPOT))
    from src.core import sauvegardes
    from src.core.game_data import load_catalog
    racines = sauvegardes.racines()
    trouves: list[tuple[str, Path]] = []
    for jeu in load_catalog().games:
        spec = jeu.sauvegardes
        base = racines.get(spec.racine) if spec else None
        if spec is None or base is None or not base.is_dir():
            continue
        for motif in spec.dossiers:
            try:
                for p in base.glob(motif):
                    # Le dossier de PREMIER niveau entier : HP1-HP3 y rangent aussi leur configuration.
                    haut = base / p.relative_to(base).parts[0]
                    if p.is_dir() and (spec.racine, haut) not in trouves:
                        trouves.append((spec.racine, haut))
            except (OSError, ValueError):
                continue
    return trouves


def preparer_isolement(sortie: Path, jeux_copie: Path | None, seuil_mo: int) -> dict:
    """Le dossier personnel du banc, ses copies, et la config muette. Rend les chemins."""
    iso = sortie / "isolement"
    maison = iso / "maison"
    launcher = maison / "Games" / "AccioLauncher" / "_Launcher"
    launcher.mkdir(parents=True, exist_ok=True)
    reel = JEUX_REELS / "_Launcher"
    for nom in ("catalog_cache.json", "sessions.json", "sauvegardes.json", "musiques_vues.json", "succes.json"):
        _copier_arbre(reel / nom, launcher / nom)
    if not (launcher / "trailers").is_dir():
        _copier_arbre(reel / "trailers", launcher / "trailers")
    if not (launcher / "cache").is_dir():
        # Les caches du joueur (vignettes, morceaux et cinématiques convertis) : « telle quelle ».
        _copier_arbre(reel / "cache", launcher / "cache", sauf=tuple(
            p.name for p in (reel / "cache").glob("*.exe")))
    # Qt suit USERPROFILE pour Images : sans copie, la galerie du banc serait vide.
    captures = maison / "Pictures" / "Accio Launcher"
    if not captures.is_dir():
        _copier_arbre(Path.home() / "Pictures" / "Accio Launcher", captures)
    documents, appdata = iso / "documents", iso / "localappdata"
    if not documents.is_dir() and not appdata.is_dir():
        for racine, dossier in _dossiers_sauvegardes():
            _copier_arbre(dossier, (documents if racine == "documents" else appdata) / dossier.name)
    documents.mkdir(parents=True, exist_ok=True)
    appdata.mkdir(parents=True, exist_ok=True)
    jeux = jeux_copie
    bilan_copie = None
    if jeux is None:
        jeux = sortie / "jeux_copie"
        if not (jeux / ".banc_complet").exists():
            print(f"Copie partielle des jeux vers {jeux} (≤ {seuil_mo} Mo par fichier)…", flush=True)
            bilan_copie = copier_jeux_partiels(JEUX_REELS, jeux, seuil_mo)
    donnees = json.loads((reel / "config.json").read_text(encoding="utf-8"))
    donnees.update(install_path=str(jeux), cache_path=str(launcher / "cache"), son_coupe=True,
                   musique_fond="", discord_presence=False, discord_partie=False, couleur_manette=False,
                   navigation_manette=False, copies_sauvegardes=False)
    (launcher / "config.json").write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"racine": str(iso), "maison": str(maison), "documents": str(documents),
            "localappdata": str(appdata), "jeux": str(jeux), "copie": bilan_copie}


# ════════════════════════════ Profils et processus enfants ════════════════════════════

def env_profil(profil: str, mode: str, carte: str, maison: str) -> dict:
    env = dict(os.environ)
    env.update(HOME=maison, USERPROFILE=maison, PYTHONIOENCODING="utf-8")
    for cle in ("QT_QUICK_BACKEND", "QSG_RHI_BACKEND", "QSG_RHI_PREFER_SOFTWARE_RENDERER", "QSG_RENDER_TIMING",
                "ACCIO_FOND_GPU", "ACCIO_FICHE_GPU", "ACCIO_CARROUSEL_GPU", "ACCIO_MEDIA_GPU"):
        env.pop(cle, None)
    if mode == "hors-ecran":
        env["QT_QPA_PLATFORM"] = "offscreen"
    else:
        env.pop("QT_QPA_PLATFORM", None)
        env["QSG_RENDER_TIMING"] = "1"
    if profil == "vieux-pc":
        if carte == "warp":
            if sys.platform == "win32":
                env.update(QSG_RHI_BACKEND="d3d11", QSG_RHI_PREFER_SOFTWARE_RENDERER="1")
            else:
                env.update(QSG_RHI_BACKEND="opengl", LIBGL_ALWAYS_SOFTWARE="1")
        else:
            env["QT_QUICK_BACKEND"] = "software"
    return env


def _affinite_vieux_pc() -> list[int]:
    return [0, 1]


class _JobMemoire:
    """Un objet job Windows qui plafonne la mémoire PRIVÉE d'un processus (ProcessMemoryLimit).

    Ne touche que le processus mesuré ; rend aussi le pic de mémoire engagée vu par le système.
    """

    def __init__(self, octets: int) -> None:
        import ctypes
        from ctypes import wintypes

        class _Basique(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class _Io(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("R", "W", "A", "RT", "WT", "AT")]

        class _Etendu(ctypes.Structure):
            _fields_ = [("Basic", _Basique), ("Io", _Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self._ct, self._Etendu = ctypes, _Etendu
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.CreateJobObjectW.restype = wintypes.HANDLE
        self._k32.OpenProcess.restype = wintypes.HANDLE
        self.job = self._k32.CreateJobObjectW(None, None)
        if not self.job:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
        info = _Etendu()
        info.Basic.LimitFlags = 0x100          # JOB_OBJECT_LIMIT_PROCESS_MEMORY
        info.ProcessMemoryLimit = octets
        if not self._k32.SetInformationJobObject(wintypes.HANDLE(self.job), 9, ctypes.byref(info),
                                                 ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")

    def assigner(self, pid: int) -> None:
        from ctypes import wintypes
        proc = self._k32.OpenProcess(0x0100 | 0x0001 | 0x0400, False, pid)
        if not proc:
            raise OSError(self._ct.get_last_error(), "OpenProcess")
        try:
            if not self._k32.AssignProcessToJobObject(wintypes.HANDLE(self.job), wintypes.HANDLE(proc)):
                raise OSError(self._ct.get_last_error(), "AssignProcessToJobObject")
        finally:
            self._k32.CloseHandle(wintypes.HANDLE(proc))

    def pic_mo(self) -> float | None:
        from ctypes import wintypes
        info = self._Etendu()
        if not self._k32.QueryInformationJobObject(wintypes.HANDLE(self.job), 9, self._ct.byref(info),
                                                   self._ct.sizeof(info), None):
            return None
        return info.PeakProcessMemoryUsed / 2 ** 20

    def fermer(self) -> None:
        from ctypes import wintypes
        self._k32.CloseHandle(wintypes.HANDLE(self.job))


def lancer_enfant(role: str, params: dict, env: dict, sortie: Path, profil: str, delai_s: int = 900) -> dict:
    """Un processus mesuré : `role` ∈ demarrage, parcours, profil. Rend son JSON."""
    import psutil
    etiquette = f"{params['etiquette']}_{role}_{params.get('tour', 0)}"
    chemin_params = sortie / "travail" / f"{etiquette}.params.json"
    chemin_resultat = sortie / "travail" / f"{etiquette}.json"
    chemin_params.parent.mkdir(parents=True, exist_ok=True)
    chemin_resultat.unlink(missing_ok=True)
    chemin_params.write_text(json.dumps({**params, "role": role, "resultat": str(chemin_resultat)},
                                        ensure_ascii=False), encoding="utf-8")
    journal = (sortie / "travail" / f"{etiquette}.journal.txt").open("w", encoding="utf-8")
    env = dict(env, BANC_T0=repr(time.perf_counter()))
    # Ce même script, sous l'interpréteur courant : aucun argument ne vient du dehors.
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--enfant", str(chemin_params)],  # nosec B603  # noqa: S603
                            env=env, cwd=str(DEPOT), stdout=journal, stderr=subprocess.STDOUT)
    job, note_job = None, ""
    if profil == "vieux-pc":
        try:
            if sys.platform == "win32":
                psutil.Process(proc.pid).cpu_affinity(_affinite_vieux_pc())
            else:
                os.sched_setaffinity(proc.pid, set(_affinite_vieux_pc()))
        except (OSError, psutil.Error, AttributeError) as exc:
            note_job += f"affinité refusée : {exc} ; "
        if sys.platform == "win32":
            try:
                job = _JobMemoire(int(CIBLES["memoire_plafond_mo"]) * 2 ** 20)
                job.assigner(proc.pid)
            except OSError as exc:
                note_job += f"plafond de mémoire non posé ({exc}) : pic seulement comparé à 4 Go ; "
                job = None
    try:
        code = proc.wait(timeout=delai_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = "délai dépassé"
    journal.close()
    resultat = {"erreurs": [f"{role} : processus sans résultat (code {code})"]}
    if chemin_resultat.exists():
        resultat = json.loads(chemin_resultat.read_text(encoding="utf-8"))
    resultat["code"] = code
    if job is not None:
        resultat["pic_job_mo"] = job.pic_mo()
        job.fermer()
    if note_job:
        resultat.setdefault("notes", []).append(note_job.rstrip("; "))
    return resultat


def _commit() -> str:
    # Chemin ABSOLU de git : jamais un programme lancé par son seul nom (test_securite).
    git = shutil.which("git")
    if git is None:
        return "?"
    try:
        sortie = subprocess.run([git, "-C", str(DEPOT), "rev-parse", "--short", "HEAD"],  # nosec B603  # noqa: S603
                                capture_output=True, text=True, encoding="utf-8", timeout=10, check=False)
        etat = subprocess.run([git, "-C", str(DEPOT), "status", "--porcelain", "--", "src"],  # nosec B603  # noqa: S603
                              capture_output=True, text=True, encoding="utf-8", timeout=10, check=False)
        return sortie.stdout.strip() + (" + src modifié" if etat.stdout.strip() else "")
    except OSError:
        return "?"


def _resumer_profil(chemin: Path, sortie_txt: Path) -> None:
    import io
    import pstats
    flux = io.StringIO()
    st = pstats.Stats(str(chemin), stream=flux)
    st.sort_stats("cumulative").print_stats(r"src[\\/]|main\.py", 45)
    st.sort_stats("tottime").print_stats(30)
    sortie_txt.write_text(flux.getvalue(), encoding="utf-8")


def assembler(args, iso: dict, demarrages: list[dict], parcours: dict, profil_res: dict | None) -> dict:
    tours = [d for d in demarrages if d.get("utilisable_ms") is not None]
    mesures = tours if args.froid else tours[1:] or tours
    res = dict(parcours)
    res["meta"] = {
        "etiquette": args.etiquette, "profil": args.profil, "mode": args.mode,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "commit": _commit(),
        "python": sys.version.split()[0], "qt": parcours.get("qt", "?"),
        "rendu": parcours.get("rendu", ""),
        "affinite": "2 cœurs (0, 1)" if args.profil == "vieux-pc" else "",
        "plafond_memoire": ("4 Go de mémoire privée (objet job)" if sys.platform == "win32" else
                            "mesuré seulement (Linux)") if args.profil == "vieux-pc" else "",
        "jeux_copie": iso["jeux"],
    }
    res["demarrage"] = {
        "froid": args.froid, "tours": demarrages,
        "mediane_premier_paint_ms": statistics.median([d["premier_paint_ms"] for d in mesures
                                                       if d.get("premier_paint_ms") is not None])
        if mesures else None,
        "mediane_utilisable_ms": statistics.median([d["utilisable_ms"] for d in mesures]) if mesures else None,
    }
    erreurs = list(parcours.get("erreurs", []))
    for d in demarrages:
        erreurs += d.get("erreurs", [])
    if parcours.get("pic_job_mo") is not None:
        res.setdefault("memoire", {})["pic_job_mo"] = parcours["pic_job_mo"]
    if profil_res is not None:
        res["profils"] = dict(profil_res.get("profils", {}), **{
            f"{nom} (fil principal)": chemin for nom, chemin in profil_res.get("profils_fil_principal", {}).items()})
        res["actions_profilees"] = profil_res.get("actions", [])
        erreurs += profil_res.get("erreurs", [])
    res["erreurs"] = erreurs
    limites = list(LIMITES)
    if args.mode == "hors-ecran":
        limites.append("Hors écran, Qt Quick rend en LOGICIEL (journal : « carte graphique (Software) ») : le "
                       "processeur y fait le travail de la carte graphique, la part d'un cœur est donc SURESTIMÉE "
                       "au repos et pendant une vidéo, et le profil vieux-pc n'y change pas le rendu (seuls les "
                       "deux cœurs et le plafond de mémoire comptent).")
    res["limites"] = limites + (parcours.get("notes") or [])
    return res


LIMITES = [
    "Hors écran, l'affichage est sous-estimé : la composition de la fenêtre et la carte graphique "
    "n'y travaillent pas comme à l'écran ; les scènes Qt Quick n'ont pas de temps de rendu.",
    "La réponse s'arrête au dernier paint du fil d'interface avant un battement revenu à l'heure "
    "(seuil 16 ms) : le travail d'un autre fil (décodage, lecture des sauvegardes) n'y compte pas.",
    "Lectures Qt comptées à la construction (QPixmap, QImage, QIcon, QFile, QImageReader avec un "
    "chemin) : une QIcon chargée paresseusement est comptée à sa création, pas à sa lecture.",
    "Échappent au comptage par fichier : les sources `file:` des scènes QML (Image, VideoOutput), "
    "les vidéos lues par QMediaPlayer, les polices et extensions chargées par Qt lui-même ; "
    "les octets lus par tout le processus (compteurs du système) les couvrent en total.",
    "Le démarrage est celui des SOURCES (`main.main`), pas de l'exe PyInstaller (décompression en plus).",
    "Les fichiers de plus de 64 Mo des jeux sont vides dans la copie : ce qui les lit (music.big, "
    "vidéos de jeu) montre un cas « sans contenu ».",
    "Personnages et Bestiaire : hors écran, le modèle 3D est peint par QPainter (repli documenté de "
    "`modele_3d_gpu` sur la plateforme offscreen, 22 à 66 ms par image) ; leurs blocages ne valent que "
    "pour une machine sans OpenGL 2.1, la vraie fenêtre tranche.",
    "cProfile (Python 3.12+) instrumente tous les fils : le fichier `_fil_principal.txt` (échantillons de "
    "la pile du seul fil d'interface, une par milliseconde au mieux, moins quand le GIL est tenu) est "
    "celui qui attribue le temps du fil d'interface.",
    "La machine est partagée pendant la mesure (autres processus) : d'un lancement à l'autre, le démarrage "
    "varie de plusieurs dizaines de millisecondes ; comparer des médianes de plusieurs tours.",
]


def principal(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Banc de rapidité du launcher (voir la docstring).")
    ap.add_argument("--profil", choices=("ludo", "vieux-pc"), default="ludo")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--hors-ecran", dest="mode", action="store_const", const="hors-ecran")
    mode.add_argument("--vraie-fenetre", dest="mode", action="store_const", const="vraie-fenetre")
    ap.set_defaults(mode="hors-ecran")
    ap.add_argument("--carte", choices=("software", "warp"), default="software",
                    help="vieux-pc : rendu Qt Quick logiciel, ou carte graphique logicielle WARP")
    ap.add_argument("--froid", action="store_true",
                    help="un seul démarrage, à lancer JUSTE APRÈS un redémarrage (le banc ne vide aucun cache)")
    ap.add_argument("--repetitions", type=int, default=3, help="démarrages mesurés à chaud (plus un jeté)")
    ap.add_argument("--repos-s", type=float, default=10.0)
    ap.add_argument("--sans-profilage", action="store_true")
    ap.add_argument("--jeux-copie", default=None)
    ap.add_argument("--seuil-copie-mo", type=int, default=SEUIL_COPIE_MO)
    ap.add_argument("--sortie", default=str(SORTIE_DEFAUT))
    ap.add_argument("--etiquette", default=None)
    ap.add_argument("--enfant", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.enfant:
        return enfant(Path(args.enfant))
    args.etiquette = args.etiquette or f"{args.profil}_{args.mode}"
    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    iso = preparer_isolement(sortie, _trouver_jeux_copie(args.jeux_copie, sortie), args.seuil_copie_mo)
    env = env_profil(args.profil, args.mode, args.carte, iso["maison"])
    params = {"etiquette": args.etiquette, "iso": iso, "mode": args.mode, "profil": args.profil,
              "repos_s": args.repos_s, "sortie": str(sortie)}
    demarrages = []
    for tour in range(1 if args.froid else 1 + args.repetitions):
        print(f"Démarrage {tour + 1}…", flush=True)
        demarrages.append(lancer_enfant("demarrage", {**params, "tour": tour}, env, sortie, args.profil,
                                        delai_s=120))
    print("Parcours…", flush=True)
    parcours = lancer_enfant("parcours", params, env, sortie, args.profil)
    profil_res = None
    if not args.sans_profilage:
        print("Profilage…", flush=True)
        profil_res = lancer_enfant("profil", params, env, sortie, args.profil)
        for nom, chemin in (profil_res.get("profils") or {}).items():
            _resumer_profil(Path(chemin), Path(chemin).with_suffix(".txt"))
            profil_res["profils"][nom] = str(Path(chemin).with_suffix(".txt"))
    res = assembler(args, iso, demarrages, parcours, profil_res)
    (sortie / f"{args.etiquette}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    (sortie / f"{args.etiquette}.md").write_text(rendre_markdown(res), encoding="utf-8")
    print(f"Rapport : {sortie / (args.etiquette + '.md')}")
    return 0


# ════════════════════════════ Processus mesuré (enfant) ════════════════════════════

class Garde:
    """Crochet d'audit : compte les lectures par fichier, REFUSE les écritures hors du banc et le réseau."""

    _ECRITURES = ("os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.replace", "shutil.rmtree",
                  "os.truncate", "os.chmod", "os.utime", "shutil.copyfile", "shutil.move")

    def __init__(self, autorises: list[str]) -> None:
        self.autorises = [os.path.normcase(os.path.abspath(a)) for a in autorises]
        self.lectures: Counter = Counter()
        self.origine: dict[str, set] = {}
        self.phase = "démarrage"
        self.phases: dict[str, set] = {}
        self.listes: Counter = Counter()
        self.refus: list[str] = []
        self.actif = True

    def _permis(self, chemin) -> bool:
        try:
            c = os.path.normcase(os.path.abspath(os.fsdecode(chemin)))
        except (TypeError, ValueError):
            return True
        return "__pycache__" in c or c == os.devnull or any(c.startswith(a) for a in self.autorises)

    def lire(self, chemin, origine: str = "python") -> None:
        if not self.actif:
            return
        try:
            c = os.path.abspath(os.fsdecode(chemin))
        except (TypeError, ValueError):
            return
        self.lectures[c] += 1
        self.origine.setdefault(c, set()).add(origine)
        self.phases.setdefault(c, set()).add(self.phase)

    def __call__(self, evenement: str, args: tuple) -> None:
        if evenement == "open":
            chemin, mode, drapeaux = (tuple(args) + (None, None, None))[:3]
            if isinstance(chemin, int) or chemin is None:
                return
            ecrit = (any(m in mode for m in "wax+") if isinstance(mode, str)
                     else bool((drapeaux or 0) & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC)))
            if ecrit:
                if not self._permis(chemin):
                    self.refus.append(f"écriture refusée : {chemin}")
                    raise PermissionError(f"banc de rapidité : écriture hors du banc refusée ({chemin})")
                return
            self.lire(chemin)
        elif evenement in self._ECRITURES:
            for chemin in [a for a in args if isinstance(a, (str, bytes, os.PathLike))][:2]:
                if not self._permis(chemin):
                    self.refus.append(f"{evenement} refusé : {chemin}")
                    raise PermissionError(f"banc de rapidité : {evenement} hors du banc refusé ({chemin})")
        elif evenement in ("os.listdir", "os.scandir") and self.actif:
            if args and isinstance(args[0], (str, bytes, os.PathLike)):
                self.listes[os.fsdecode(args[0])] += 1
        elif evenement == "socket.connect":
            adresse = args[1] if len(args) > 1 else None
            hote = adresse[0] if isinstance(adresse, tuple) and adresse else adresse
            if hote not in ("127.0.0.1", "::1", "localhost") and not isinstance(hote, (bytes, type(None))):
                self.refus.append(f"réseau refusé : {adresse}")
                raise PermissionError("banc de rapidité : réseau coupé")
        elif evenement == "socket.getaddrinfo":
            if args and args[0] not in ("127.0.0.1", "::1", "localhost", None):
                self.refus.append(f"résolution refusée : {args[0]}")
                raise PermissionError("banc de rapidité : réseau coupé")


def _compter_qt(garde: Garde) -> list[str]:
    """Remplace les classes Qt qui LISENT un fichier par des sous-classes qui le comptent.

    Une métaclasse garde `isinstance` vrai pour les objets créés par Qt (classe de base)."""
    from PyQt6 import QtCore, QtGui
    enveloppes = []

    def envelopper(module, nom: str, methodes: tuple[str, ...] = ()) -> None:
        base = getattr(module, nom, None)
        if base is None:
            return

        class _Meta(type(base)):
            def __instancecheck__(cls, obj):
                return isinstance(obj, base)

            def __subclasscheck__(cls, sous):
                return issubclass(sous, base)

        def __init__(self, *a, **k):
            if a and isinstance(a[0], str) and a[0] and not a[0].startswith(":"):
                garde.lire(a[0], nom)
            base.__init__(self, *a, **k)

        attributs = {"__init__": __init__}
        for m in methodes:
            def lecture(self, *a, _m=m, **k):
                if a and isinstance(a[0], str) and a[0] and not a[0].startswith(":"):
                    garde.lire(a[0], f"{nom}.{_m}")
                return getattr(base, _m)(self, *a, **k)
            attributs[m] = lecture
        setattr(module, nom, _Meta(nom, (base,), attributs))
        enveloppes.append(nom)

    envelopper(QtGui, "QPixmap", ("load",))
    envelopper(QtGui, "QImage", ("load",))
    envelopper(QtGui, "QImageReader", ("setFileName",))
    envelopper(QtGui, "QIcon", ("addFile",))
    envelopper(QtGui, "QMovie", ("setFileName",))
    envelopper(QtCore, "QFile", ("setFileName",))
    try:
        from PyQt6 import QtSvg
        envelopper(QtSvg, "QSvgRenderer", ("load",))
    except ImportError:
        pass
    police = QtGui.QFontDatabase.addApplicationFont

    def ajouter_police(chemin):
        garde.lire(chemin, "addApplicationFont")
        return police(chemin)
    QtGui.QFontDatabase.addApplicationFont = staticmethod(ajouter_police)
    enveloppes.append("QFontDatabase.addApplicationFont")
    return enveloppes


class Memoire:
    def __init__(self) -> None:
        import psutil
        self.proc = psutil.Process()
        self.mesure = "octets privés (PrivateUsage)" if sys.platform == "win32" else "RSS"

    def mo(self) -> float:
        info = self.proc.memory_info()
        return getattr(info, "private", info.rss) / 2 ** 20


class Sentinelle(threading.Thread):
    """Surveille le battement du fil principal ; pendant un blocage, échantillonne sa pile."""

    def __init__(self, ident_principal: int, memoire: Memoire, seuil_s: float = 0.050) -> None:
        super().__init__(daemon=True, name="sentinelle-banc")
        self.ident_principal = ident_principal
        self.memoire = memoire
        self.seuil = seuil_s
        self.battement = time.perf_counter()
        self.actif = False
        self.etape = "démarrage"
        self.blocages: list[dict] = []
        self.pic = 0.0
        self.dormir = False      # mesure du processeur : la sentinelle se fait oublier
        self._arret = False

    def remettre_pic(self) -> None:
        self.pic = self.memoire.mo()

    def _pile(self) -> list[tuple[str, int, str]]:
        cadre = sys._current_frames().get(self.ident_principal)
        pile = []
        while cadre is not None and len(pile) < 40:
            pile.append((cadre.f_code.co_filename, cadre.f_lineno, cadre.f_code.co_name))
            cadre = cadre.f_back
        return pile

    def run(self) -> None:
        dernier_mem = 0.0
        en_blocage, debut, echantillons, etape = False, 0.0, [], ""
        while not self._arret:
            time.sleep(0.25 if self.dormir else 0.002 if self.actif else 0.02)
            maintenant = time.perf_counter()
            if maintenant - dernier_mem > 0.02:
                dernier_mem = maintenant
                try:
                    self.pic = max(self.pic, self.memoire.mo())
                except Exception:   # processus mesuré déjà parti : le pic garde sa valeur
                    _LOG.debug("mémoire illisible", exc_info=True)
            if not self.actif:
                en_blocage = False
                continue
            retard = maintenant - self.battement
            if retard > self.seuil:
                if not en_blocage:
                    en_blocage, debut, echantillons, etape = True, self.battement, [], self.etape
                if len(echantillons) < 400:
                    echantillons.append(self._pile())
            elif en_blocage:
                en_blocage = False
                self.blocages.append({"debut": debut, "fin": self.battement, "etape": etape,
                                      "echantillons": echantillons})

    def arreter(self) -> None:
        self._arret = True


class Echantillonneur(threading.Thread):
    """Profil du SEUL fil principal, par échantillons de pile toutes les millisecondes.

    cProfile (Python 3.12+) instrumente tous les fils à la fois : ses chiffres mêlent ce que font
    les fils de lecture au travail du fil d'interface. Ici, rien que le fil principal."""

    def __init__(self, ident_principal: int) -> None:
        super().__init__(daemon=True, name="echantillonneur-banc")
        self.ident_principal = ident_principal
        self.actif = False
        self.piles: Counter = Counter()
        self.duree = 0.0

    def vider(self) -> None:
        self.piles.clear()
        self.duree = 0.0

    def run(self) -> None:
        precedent = time.perf_counter()
        while True:
            time.sleep(0.001)
            maintenant = time.perf_counter()
            if self.actif:
                self.duree += maintenant - precedent
                cadre = sys._current_frames().get(self.ident_principal)
                pile = []
                while cadre is not None and len(pile) < 60:
                    if "banc_rapidite" not in cadre.f_code.co_filename:
                        pile.append((_court(cadre.f_code.co_filename), cadre.f_lineno, cadre.f_code.co_name,
                                     cadre.f_code.co_firstlineno))
                    cadre = cadre.f_back
                self.piles[tuple(pile)] += 1
            precedent = maintenant

    def rapport(self, nom: str) -> str:
        total = sum(self.piles.values()) or 1
        ms = self.duree * 1000 / total
        inclusif: Counter = Counter()
        par_ligne: Counter = Counter()
        exclusif: Counter = Counter()
        for pile, n in self.piles.items():
            if pile:
                exclusif[f"{pile[0][0]}:{pile[0][1]} {pile[0][2]}"] += n
            for f, _ligne, fn, debut in set((c[0], 0, c[2], c[3]) for c in pile):
                inclusif[f"{f}:{debut} {fn}"] += n
            for f, ligne, fn, _debut in set(pile):
                par_ligne[f"{f}:{ligne} {fn}"] += n
        du_depot = ("src/", "main.py")
        lignes = [f"Fil principal, {nom} : {total} échantillons sur {self.duree * 1000:.0f} ms "
                  f"(≈ {ms:.2f} ms par échantillon). Fonctions du dépôt (src/, main.py), temps inclusif, "
                  "ligne de leur définition :", ""]
        lignes += [f"{n * ms:9.1f} ms  {cle}" for cle, n in inclusif.most_common(400)
                   if cle.startswith(du_depot)][:60]
        lignes += ["", "Lignes du dépôt sur la pile (temps inclusif, la ligne qui appelle) :", ""]
        lignes += [f"{n * ms:9.1f} ms  {cle}" for cle, n in par_ligne.most_common(600)
                   if cle.startswith(du_depot)][:80]
        lignes += ["", "Ligne exacte en cours (temps exclusif, tout le code, C++ compté sur la ligne Python "
                   "qui l'appelle) :", ""]
        lignes += [f"{n * ms:9.1f} ms  {cle}" for cle, n in exclusif.most_common(60)]
        return "\n".join(lignes) + "\n"


_DEPOT_NORM = os.path.normcase(str(DEPOT)) + os.sep


_COURTS: dict[str, str] = {}


def _court(fichier: str) -> str:
    court = _COURTS.get(fichier)
    if court is None:
        norm = os.path.normcase(os.path.abspath(fichier))
        court = norm[len(_DEPOT_NORM):].replace(os.sep, "/") if norm.startswith(_DEPOT_NORM) else Path(fichier).name
        _COURTS[fichier] = court
    return court


def analyser_blocage(bloc: dict, depot: Path = DEPOT) -> dict:
    """La cause d'un blocage : le cadre du dépôt (hors tools/) le plus profond, le plus fréquent."""
    causes: Counter = Counter()
    piles: Counter = Counter()
    racine = os.path.normcase(str(depot)) + os.sep
    for pile in bloc["echantillons"]:
        # Ni le banc, ni `main.main` (son `app.exec()` : la boucle de Qt, sans Python au-dessus).
        cadres = [f"{_court(f)}:{ligne} {fn}" for f, ligne, fn in pile
                  if not f.startswith("<") and os.path.normcase(os.path.abspath(f)).startswith(racine)
                  and "banc_rapidite" not in f and not (fn == "main" and f.endswith("main.py"))]
        cause = cadres[0] if cadres else "Qt (aucun cadre Python du dépôt au-dessus de la boucle)"
        # Un import (paresseux : résolu au premier usage) au-dessus du premier cadre du dépôt : le dire.
        premier = next((k for k, (f, _l, fn) in enumerate(pile)
                        if not f.startswith("<") and f"{_court(f)}:{_l} {fn}" in cadres[:1]), len(pile))
        if any(f.startswith("<frozen importlib") for f, _l, _fn in pile[:premier]):
            cause = f"import d'un module ← {cause}"
        causes[cause] += 1
        piles[tuple(cadres[:8])] += 1
    cause = causes.most_common(1)[0][0] if causes else "?"
    pile = list(piles.most_common(1)[0][0]) if piles else []
    # L'appel responsable : le cadre le plus profond présent dans 80 % des échantillons au moins.
    presence: Counter = Counter()
    for cadres in piles.elements():
        presence.update(set(cadres))
    n = sum(piles.values())
    appel = next((c for c in pile if n and presence[c] >= 0.8 * n), cause)
    return {"etape": bloc["etape"], "duree_ms": (bloc["fin"] - bloc["debut"]) * 1000, "cause": cause,
            "appel": appel, "pile": pile, "echantillons": len(bloc["echantillons"])}


def enfant(chemin_params: Path) -> int:
    t_entree = time.perf_counter()
    p = json.loads(chemin_params.read_text(encoding="utf-8"))
    role = p["role"]
    if p["profil"] == "vieux-pc":
        try:
            import psutil
            if sys.platform == "win32":
                psutil.Process().cpu_affinity(_affinite_vieux_pc())
            else:
                os.sched_setaffinity(0, set(_affinite_vieux_pc()))
        except Exception:   # affinité refusée : le profil le note, la mesure continue
            _LOG.warning("affinité processeur non posée", exc_info=True)
    profileur = None
    if role == "profil":
        import cProfile
        profileur = cProfile.Profile()
        profileur.enable()
    try:
        t0 = float(os.environ.get("BANC_T0", "nan"))
    except ValueError:
        t0 = float("nan")
    if not (0 <= t_entree - t0 < 60):
        t0 = t_entree
    sys.path.insert(0, str(DEPOT))
    os.chdir(DEPOT)
    iso = p["iso"]
    garde = Garde([iso["racine"], p["sortie"], tempfile.gettempdir()])
    sys.addaudithook(garde)
    garde.actif = role == "parcours"
    from src.ui.imports_paresseux import activer
    activer()
    enveloppes = _compter_qt(garde) if role == "parcours" else []
    from src.core import config as config_mod
    documents, appdata = Path(iso["documents"]), Path(iso["localappdata"])
    config_mod.get_documents_dir = lambda: documents
    from src.core import sauvegardes
    sauvegardes.racines = lambda: {"documents": documents, "localappdata": appdata}
    banc = Banc(p, t0, t_entree, garde, profileur, enveloppes)
    banc.lancer()
    return 0


class Banc:
    """Le processus mesuré : vrai `main.main`, instrumenté, puis le parcours."""

    def __init__(self, p: dict, t0: float, t_entree: float, garde: Garde, profileur, enveloppes) -> None:
        self.p, self.t0, self.garde, self.profileur = p, t0, garde, profileur
        self.role = p["role"]
        self.res: dict = {"role": self.role, "entree_ms": (t_entree - t0) * 1000, "etapes": {},
                          "erreurs": [], "actions": [], "notes": [], "qt_enveloppes": enveloppes}
        self.memoire = Memoire()
        self.sentinelle = Sentinelle(threading.get_ident(), self.memoire)
        self.echantillonneur = Echantillonneur(threading.get_ident())
        self.images: list[list[float]] = []
        self.battements: list[tuple[float, float]] = []   # (instant, retard) des battements en retard
        self.fenetre = None
        self.t_premier_paint: float | None = None
        self._attente_paint = None
        self._attente_battement = None
        self._dernier_battement = 0.0
        self.quick: list[tuple[str, float]] = []
        self._messages: Counter = Counter()
        self._fini = False

    # ── Démarrage ──

    def lancer(self) -> None:
        import main as main_mod
        from src.core import demarrage, manette
        from src.ui import single_instance

        single_instance.SingleInstance.try_acquire = lambda self, *a, **k: True
        manette.colorer_en_fond = lambda *a, **k: None
        vraie_annonce = demarrage.annoncer

        def annoncer(etape: str) -> None:
            self.res["etapes"][etape] = (time.perf_counter() - self.t0) * 1000
            if etape == demarrage.BIBLIOTHEQUE:
                self._neutraliser_reseau()
            if etape == demarrage.FENETRE:
                self._brancher_fenetre()
            vraie_annonce(etape)
        demarrage.annoncer = annoncer
        main_mod._sortir = self._sortie_imprevue
        self._installer_messages()
        if self.role == "profil":
            self.echantillonneur.actif = True
            self.echantillonneur.start()
        else:
            self.sentinelle.start()
        try:
            main_mod.main()
        except SystemExit:
            pass
        except BaseException as exc:
            import traceback
            self.res["erreurs"].append(f"main : {exc!r} {traceback.format_exc()[-1500:]}")
        self._ecrire()

    def _neutraliser_reseau(self) -> None:
        from src.ui.main_window import MainWindow
        from src.ui.trailer_store import TrailerStore
        MainWindow._start_update_check = lambda self: None
        TrailerStore.armer_rattrapage = lambda self, config: None

    def _installer_messages(self) -> None:
        from PyQt6.QtCore import qInstallMessageHandler
        import re
        motif = re.compile(r"(\d+(?:\.\d+)?)\s*ms")

        def messages(_type, contexte, message):
            categorie = getattr(contexte, "category", "") or ""
            if categorie.startswith("qt.scenegraph.time") or "Frame rendered" in message:
                nombres = motif.findall(message)
                if nombres:
                    self.quick.append((categorie or "scenegraph", float(nombres[0])))
                return
            try:
                self._messages[message[:160]] += 1
            except Exception:   # un message Qt illisible ne doit pas casser la mesure
                _LOG.debug("message Qt ignoré", exc_info=True)
        qInstallMessageHandler(messages)

    def _sortie_imprevue(self, code: int) -> None:
        self.res["erreurs"].append(f"le launcher a voulu sortir (code {code}) avant la fin du banc")
        self._ecrire()

    def _brancher_fenetre(self) -> None:
        from PyQt6.QtCore import QObject, QTimer, Qt
        from PyQt6.QtWidgets import QApplication
        fen = next((w for w in QApplication.topLevelWidgets() if type(w).__name__ == "MainWindow"), None)
        if fen is None:
            self.res["erreurs"].append("MainWindow introuvable à l'annonce de la fenêtre")
            return
        self.fenetre = fen
        banc = self

        class _Filtre(QObject):
            def eventFilter(self, obj, ev):  # noqa: N802 (Qt)
                t = ev.type()
                if t == ev.Type.UpdateRequest or (t == ev.Type.Paint and banc.t_premier_paint is None):
                    debut = time.perf_counter()
                    obj.event(ev)
                    fin = time.perf_counter()
                    banc._sur_image(debut, fin)
                    return True
                return False
        self._filtre = _Filtre()
        fen.installEventFilter(self._filtre)
        self._battement = QTimer()
        self._battement.setTimerType(Qt.TimerType.PreciseTimer)
        self._battement.setInterval(5)
        self._battement.timeout.connect(self._sur_battement)
        self._battement.start()
        self._t_battement_prec = time.perf_counter()
        self._suite_a_l_heure = 0

    def _sur_image(self, debut: float, fin: float) -> None:
        self.images.append([debut, fin])
        if self.t_premier_paint is None:
            self.t_premier_paint = fin
            self.res["premier_paint_ms"] = (fin - self.t0) * 1000
        if self._attente_paint is not None:
            rappel, apres = self._attente_paint
            if debut >= apres or fin > apres:
                self._attente_paint = None
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: rappel(fin))

    def _sur_battement(self) -> None:
        maintenant = time.perf_counter()
        retard = maintenant - self._t_battement_prec - 0.005
        self._t_battement_prec = maintenant
        self.sentinelle.battement = maintenant
        if retard > 0.016:
            self.battements.append((maintenant, retard))
        if self._attente_battement is not None:
            rappel = self._attente_battement
            self._attente_battement = None
            rappel(maintenant, retard)
        if self.t_premier_paint is not None and "utilisable_ms" not in self.res:
            self._suite_a_l_heure = self._suite_a_l_heure + 1 if retard < 0.008 else 0
            if self._suite_a_l_heure == 1:
                self._debut_suite = maintenant
            if self._suite_a_l_heure >= 5:
                self.res["utilisable_ms"] = (self._debut_suite - self.t0) * 1000
                self._apres_demarrage()

    def _apres_demarrage(self) -> None:
        from PyQt6.QtCore import QTimer
        if self.role == "demarrage":
            self._ecrire()
            return
        if self.role == "profil" and self.profileur is not None:
            self.profileur.disable()
            self.echantillonneur.actif = False
            self._sauver_profil("demarrage")
        self.garde.phase = "parcours"
        self.res["memoire_apres_demarrage_mo"] = self.memoire.mo()
        self._pilote = Pilote(self, self._parcours() if self.role == "parcours" else self._parcours_profil())
        QTimer.singleShot(0, self._pilote.suivant)

    def _sauver_profil(self, nom: str) -> None:
        dossier = Path(self.p["sortie"]) / f"{self.p['etiquette']}_profils"
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / f"{nom}.prof"
        self.profileur.dump_stats(str(chemin))
        self.res.setdefault("profils", {})[nom] = str(chemin)
        fil = dossier / f"{nom}_fil_principal.txt"
        fil.write_text(self.echantillonneur.rapport(nom), encoding="utf-8")
        self.res.setdefault("profils_fil_principal", {})[nom] = str(fil)

    def _ecrire(self) -> None:
        if self._fini:
            return
        self._fini = True
        self.sentinelle.arreter()
        try:
            self.res["refus"] = self.garde.refus
            if self.role == "parcours":
                self._conclure()
            self.res["messages_qt"] = dict(self._messages.most_common(20))
            Path(self.p["resultat"]).write_text(json.dumps(self.res, ensure_ascii=False, indent=1, default=str),
                                                encoding="utf-8")
        finally:
            import logging
            logging.shutdown()
            sys.stdout.flush()
            os._exit(0)

    # ── Mesure d'une action ──

    def attendre_paint(self, apres: float, rappel) -> None:
        self._attente_paint = (rappel, apres)

    def attendre_battement(self, rappel) -> None:
        self._attente_battement = rappel

    def _conclure(self) -> None:
        blocs = [analyser_blocage(b) for b in self.sentinelle.blocages]
        self.res["blocages"] = blocs
        cumul: dict[str, list[float]] = {}
        for b in blocs:
            cumul.setdefault(b["cause"], []).append(b["duree_ms"])
        self.res["causes"] = sorted(({"cause": c, "n": len(v), "total_ms": sum(v)} for c, v in cumul.items()),
                                    key=lambda c: -c["total_ms"])
        lectures = self.garde.lectures
        relus, fichiers, modules = [], 0, 0
        for chemin, n in lectures.items():
            if chemin.lower().endswith(_MODULES):
                modules += n
                continue
            fichiers += 1
            if n > 1:
                try:
                    taille = os.path.getsize(chemin)
                except OSError:
                    taille = None
                relus.append({"fichier": chemin, "lectures": n, "taille": taille,
                              "origine": ", ".join(sorted(self.garde.origine.get(chemin, ()))),
                              "phases": sorted(self.garde.phases.get(chemin, ()))})
        relus.sort(key=lambda r: (-r["lectures"] * (r["taille"] or 1)))
        try:
            octets = self.memoire.proc.io_counters().read_bytes
        except Exception:
            octets = None
        self.res["disque"] = {
            "fichiers": fichiers, "lectures": sum(n for c, n in lectures.items() if not c.lower().endswith(_MODULES)),
            "modules": modules, "relus": relus, "octets_processus": octets,
            "listes_de_dossier_repetees": [{"dossier": d, "n": n} for d, n in self.garde.listes.most_common(30)
                                           if n > 1],
            "echappe": ["sources `file:` des scènes QML (fond, vidéo)", "vidéos lues par QMediaPlayer",
                        "polices et extensions chargées par Qt lui-même",
                        "lectures C++ internes (QIcon paresseuse lue plus tard, QImageReader déjà construit)"]}
        if self.quick:
            par: dict[str, list[float]] = {}
            for cat, ms in self.quick:
                par.setdefault(cat, []).append(ms)
            self.res["quick"] = {c: {"n": len(v), "p50_ms": _p(v, 0.5), "p95_ms": _p(v, 0.95), "max_ms": max(v)}
                                 for c, v in par.items()}
        mem = self.res.setdefault("memoire", {})
        mem["pic_mo"] = max(self.sentinelle.pic, mem.get("pic_mo") or 0)
        mem["mesure"] = self.memoire.mesure
        anims = self.res.get("animations_brutes", {})
        self.res["animations"] = {nom: stats_images(sessions) for nom, sessions in anims.items()
                                  if any(sessions)}
        self.res.pop("animations_brutes", None)
        from PyQt6.QtCore import QT_VERSION_STR
        self.res["qt"] = QT_VERSION_STR
        self.res["rendu"] = self._rendu()

    def _rendu(self) -> str:
        from src.ui import carrousel_gpu, ecran_video_gpu, fiche_gpu, fond_gpu
        morceaux = [f"plateforme {os.environ.get('QT_QPA_PLATFORM', 'native')}",
                    f"QT_QUICK_BACKEND={os.environ.get('QT_QUICK_BACKEND', '')}",
                    f"QSG_RHI_BACKEND={os.environ.get('QSG_RHI_BACKEND', '')}",
                    f"QSG_RHI_PREFER_SOFTWARE_RENDERER={os.environ.get('QSG_RHI_PREFER_SOFTWARE_RENDERER', '')}"]
        try:
            fond = self.fenetre._detail._bg
            morceaux.append(f"fond : {type(fond).__name__}")
            morceaux.append("GPU actifs : " + ", ".join(
                n for n, m in (("fond", fond_gpu), ("fiche", fiche_gpu), ("carrousel", carrousel_gpu),
                               ("médias", ecran_video_gpu)) if m.actif()))
        except Exception as exc:
            morceaux.append(f"rendu illisible ({exc})")
        return " ; ".join(morceaux)

    # ── Parcours ──

    def _parcours(self):
        from src.ui.title_bar import BIBLIOTHEQUE, CARNET, COLLECTIONS, PARAMETRES
        fen = self.fenetre
        yield ("ms", 3000)        # les tâches différées du démarrage (préchargement, toasts)
        self.res["memoire"] = {"repos_mo": self.memoire.mo(), "pages": []}
        yield from self.cpu("repos", self.p.get("repos_s", 10.0))
        self.sentinelle.actif = True
        # ① Changer de jeu, chaque vignette du carrousel.
        items = list(fen._carousel._items)
        courant = fen._carousel._current_index
        for k in range(1, len(items) + 1):
            i = (courant + k) % len(items)
            yield from self.action(f"Changer de jeu → {items[i].game.id}", "jeu",
                                   lambda i=i: _cliquer(items[i]), animation="changement de jeu")
        # ② Bande-annonce : lancer, mesurer le processeur, arrêter.
        yield from self.bande_annonce()
        # ③ L'engrenage de chaque jeu installé, et chacune de ses rubriques.
        for i, item in enumerate(items):
            if fen.manager.get_state(item.game.id).name != "INSTALLED":
                continue
            if fen._carousel._current_index != i:
                yield from self.action(f"Changer de jeu → {item.game.id}", "jeu", lambda i=i: _cliquer(items[i]))
            btn = fen._detail._action_panel._btn_reglages
            if btn is None:
                continue
            yield from self.page(f"Engrenage {item.game.id}", lambda b=btn: _cliquer(b), self._rubriques_engrenage,
                                 BIBLIOTHEQUE)
        # ④ Paramètres.
        yield from self.page("Paramètres", lambda: _cliquer(fen._title_bar.onglet(PARAMETRES)),
                             self._rubriques_parametres, BIBLIOTHEQUE)
        # ⑤ Carnet : jeux, sauvegardes, rubriques, défilement.
        yield from self.page("Carnet", lambda: _cliquer(fen._title_bar.onglet(CARNET)), self._dans_le_carnet,
                             BIBLIOTHEQUE)
        # ⑥ Collections : chaque rubrique, une fiche de l'Encyclopédie, défilement de la galerie.
        yield from self.page("Collections", lambda: _cliquer(fen._title_bar.onglet(COLLECTIONS)),
                             self._dans_les_collections, BIBLIOTHEQUE)
        # ⑦ Défilement soutenu de la galerie : processeur et images.
        yield from self.defilement_soutenu(COLLECTIONS, BIBLIOTHEQUE)
        self.sentinelle.actif = False
        self.res["memoire"]["fin_mo"] = self.memoire.mo()

    def _parcours_profil(self):
        """Profilage du changement de sauvegarde du folio (le démarrage est déjà profilé)."""
        from src.ui.title_bar import CARNET
        fen = self.fenetre
        import cProfile
        self.profileur = cProfile.Profile()
        self.echantillonneur.vider()
        yield ("ms", 2500)
        _cliquer(fen._title_bar.onglet(CARNET))
        yield ("ms", 1500)
        carnet = fen._pages.page
        for jeu, bouton in list(getattr(carnet, "_boutons", {}).items()):
            _cliquer(bouton)
            yield ("ms", 800)
            folio = getattr(carnet, "_folio", None)
            lignes = list(getattr(folio, "_lignes", {}).values())
            if len(lignes) < 2:
                continue
            for ligne in lignes[1:] + lignes[:1]:
                self.echantillonneur.actif = True
                self.profileur.enable()
                _cliquer(ligne)
                t1 = time.perf_counter()
                fin = yield ("reponse", t1)
                self.profileur.disable()
                self.echantillonneur.actif = False
                self.res["actions"].append({"nom": f"[profilé] sauvegarde {jeu}", "categorie": "sauvegarde",
                                            "reponse_ms": (fin - t1) * 1000 if fin else None})
                yield ("ms", 200)
        self._sauver_profil("folio_sauvegardes")

    def action(self, nom: str, categorie: str, faire, animation: str | None = None, apres_ms: int = 350):
        """Une action mesurée : appel, réponse (dernier paint avant le calme), calme, lectures, octets lus."""
        # Rendre la main à la boucle d'abord : sans ce temps, le travail du pilote qui précède (un
        # `gc.collect()`, la fin d'une autre page) se collait à cette action en un seul blocage.
        self.sentinelle.etape = f"(entre deux actions, avant « {nom} »)"
        yield ("ms", 60)
        self.sentinelle.etape = nom
        lectures_avant = sum(self.garde.lectures.values())
        par_fichier_avant = dict(self.garde.lectures)
        try:
            octets_avant = self.memoire.proc.io_counters().read_bytes
        except Exception:
            octets_avant = 0
        n_images = len(self.images)
        t0 = time.perf_counter()
        try:
            faire()
        except Exception as exc:
            self.res["erreurs"].append(f"{nom} : {exc!r}")
            return
        t1 = time.perf_counter()
        fin = yield ("reponse", t1)
        calme = yield ("calme", t0)
        try:
            octets = self.memoire.proc.io_counters().read_bytes - octets_avant
        except Exception:
            octets = None
        self.res["actions"].append({
            "nom": nom, "categorie": categorie, "appel_ms": (t1 - t0) * 1000,
            "reponse_ms": (fin - t0) * 1000 if fin else None,
            "calme_ms": (calme - t0) * 1000 if calme else None,
            "lectures": sum(self.garde.lectures.values()) - lectures_avant, "octets_lus": octets,
            "fichiers": [f"{Path(c).name} ×{n - par_fichier_avant.get(c, 0)}" for c, n in
                         sorted(self.garde.lectures.items(), key=lambda kv: par_fichier_avant.get(kv[0], 0) - kv[1])
                         if n > par_fichier_avant.get(c, 0)][:6]})
        if animation:
            yield ("ms", max(0, 1200 - int((time.perf_counter() - t0) * 1000)))
            fenetre = [im for im in self.images[n_images:] if im[0] <= t0 + 1.2]
            self.res.setdefault("animations_brutes", {}).setdefault(animation, []).append(fenetre)
        yield ("ms", apres_ms)

    def page(self, nom: str, ouvrir, dedans, onglet_retour: str):
        """Ouvre une page (mesuré), y fait `dedans`, la ferme par l'onglet Bibliothèque (mesuré)."""
        import gc
        fen = self.fenetre
        gc.collect()
        yield ("ms", 300)
        avant = self.memoire.mo()
        self.sentinelle.remettre_pic()
        yield from self.action(f"Ouvrir {nom}", "clic", ouvrir)
        page = fen._pages.page
        if page is None:
            self.res["erreurs"].append(f"{nom} : aucune page ouverte")
            return
        yield from dedans(page)
        ouverte = self.memoire.mo()
        pic = self.sentinelle.pic
        yield from self.action(f"Revenir à la fiche (depuis {nom})", "clic",
                               lambda: _cliquer(fen._title_bar.onglet(onglet_retour)))
        gc.collect()
        yield ("ms", 1000)
        gc.collect()
        apres = self.memoire.mo()
        self.res["memoire"]["pages"].append({"page": nom, "avant_mo": avant, "pic_mo": pic, "ouverte_mo": ouverte,
                                             "apres_mo": apres, "garde_mo": apres - avant})

    def _rubriques_engrenage(self, page):
        from PyQt6.QtWidgets import QPushButton
        jeu = getattr(getattr(page, "game", None), "id", "?")
        for ident, btn in list(getattr(page, "_onglets", {}).items())[1:] + list(getattr(page, "_onglets", {})
                                                                               .items())[:1]:
            yield from self.action(f"Engrenage {jeu} : rubrique {ident}", "rubrique", lambda b=btn: _cliquer(b))
            if ident == "image" and getattr(page, "_page_img", None) is not None:
                onglets = [b for b in page._page_img.findChildren(QPushButton) if type(b).__name__ == "_Onglet"]
                for k, b in enumerate(onglets[1:] + onglets[:1]):
                    yield from self.action(f"Engrenage {jeu} : Image, {b.text().strip() or k + 1}", "rubrique",
                                           lambda b=b: _cliquer(b))

    def _rubriques_parametres(self, page):
        boutons = list(page._nav.boutons)
        for k, b in enumerate(boutons[1:] + boutons[:1]):
            yield from self.action(f"Paramètres : {b.text().strip() or k + 1}", "rubrique",
                                   lambda b=b: _cliquer(b))

    def _dans_le_carnet(self, carnet):
        boutons = dict(getattr(carnet, "_boutons", {}))
        for jeu, bouton in boutons.items():
            yield from self.action(f"Carnet : folio de {jeu}", "jeu", lambda b=bouton: _cliquer(b))
            folio = getattr(carnet, "_folio", None)
            lignes = list(getattr(folio, "_lignes", {}).values())
            for k, ligne in enumerate(lignes[1:] + lignes[:1] if len(lignes) > 1 else []):
                yield from self.action(f"Folio {jeu} : sauvegarde {k + 1}", "sauvegarde",
                                       lambda w=ligne: _cliquer(w))
            if folio is not None:
                yield from self.defiler(f"défilement du folio {jeu}", folio, pas=6)
        for cle in ("defis", "releve", "folio"):
            b = getattr(carnet, "_rubriques", {}).get(cle)
            if b is not None:
                yield from self.action(f"Carnet : rubrique {cle}", "rubrique", lambda b=b: _cliquer(b))

    def _dans_les_collections(self, page):
        rubriques = dict(getattr(page, "_rubriques", {}))
        galerie = page._pile.currentWidget()
        yield ("ms", 2000)          # les vignettes arrivent d'un fil, posées par lots
        yield from self.defiler("défilement de la galerie (Captures)", galerie, pas=20)
        for cle, bouton in list(rubriques.items())[1:]:
            yield from self.action(f"Collections : {cle}", "rubrique", lambda b=bouton: _cliquer(b))
            jeux = list(getattr(page._jeux, "_boutons", {}).values()) if hasattr(page, "_jeux") else []
            for k, b in enumerate(jeux[1:3]):
                yield from self.action(f"Collections {cle} : jeu {k + 2}", "jeu", lambda b=b: _cliquer(b))
            vue = page._encyclo.get(cle) if hasattr(page, "_encyclo") else None
            if vue is not None:
                from src.ui.encyclopedie_page import _Fiche
                fiches = [f for f in vue.findChildren(_Fiche) if f.isVisible()]
                if fiches:
                    fiche = fiches[min(1, len(fiches) - 1)]
                    yield from self.action(f"Collections {cle} : ouvrir une fiche", "clic",
                                           lambda f=fiche, v=vue: v.choisir(f))
                yield from self.defiler(f"défilement de {cle}", vue, pas=10)
        if rubriques:
            first = next(iter(rubriques.values()))
            yield from self.action("Collections : captures", "rubrique", lambda: _cliquer(first))

    def defiler(self, nom: str, racine, pas: int = 10, intervalle_ms: int = 16, sens_alterne: bool = True):
        zone = _zone_defilante(racine)
        if zone is None:
            self.res["notes"].append(f"{nom} : aucune zone à défiler")
            return
        self.sentinelle.etape = nom
        n_images = len(self.images)
        for k in range(pas * (2 if sens_alterne else 1)):
            _molette(zone, -1 if k < pas else 1)
            yield ("ms", intervalle_ms)
        yield ("ms", 300)
        self.res.setdefault("animations_brutes", {}).setdefault(
            "défilement" if "galerie" not in nom else "défilement de la galerie", []).append(self.images[n_images:])

    def cpu(self, situation: str, duree_s: float, note: str = ""):
        battement_actif = self._battement.isActive()
        sentinelle = self.sentinelle.actif
        self._battement.stop()
        self.sentinelle.actif = False
        self.sentinelle.dormir = True
        yield ("ms", 300)
        c0, w0 = self.memoire.proc.cpu_times(), time.perf_counter()
        yield ("ms", int(duree_s * 1000))
        c1, w1 = self.memoire.proc.cpu_times(), time.perf_counter()
        self.sentinelle.dormir = False
        part = ((c1.user - c0.user) + (c1.system - c0.system)) / (w1 - w0) * 100
        self.res.setdefault("processeur", []).append({"situation": situation, "part_coeur_pct": part,
                                                      "duree_s": w1 - w0, "note": note})
        if battement_actif:
            self._t_battement_prec = time.perf_counter()
            self.sentinelle.battement = self._t_battement_prec
            self._battement.start()
        self.sentinelle.actif = sentinelle

    def bande_annonce(self):
        fen = self.fenetre
        vue = fen._detail
        from src.core import trailers
        items = list(fen._carousel._items)
        avec = [i for i, it in enumerate(items) if trailers.chemin_a_jouer(it.game.id, fen.manager.trailers())]
        if not avec:
            self.res["notes"].append("aucune bande-annonce copiée : processeur non mesuré pendant une vidéo")
            return
        i = avec[0]
        if fen._carousel._current_index != i:
            yield from self.action(f"Changer de jeu → {items[i].game.id}", "jeu", lambda: _cliquer(items[i]))
        yield from self.action(f"Lire la bande-annonce de {items[i].game.id}", "clic", vue._on_replay_clicked)
        yield ("ms", 1500)
        joue = bool(getattr(vue._video, "is_playing", False))
        yield from self.cpu("bande-annonce", 10.0, note=f"{items[i].game.id}, "
                            f"{'lecture en cours' if joue else 'LECTURE NON DÉMARRÉE'}")
        try:
            vue._stop_video()
        except Exception as exc:
            self.res["erreurs"].append(f"arrêt de la bande-annonce : {exc!r}")
        yield ("ms", 500)

    def defilement_soutenu(self, onglet: str, retour: str):
        fen = self.fenetre
        yield from self.action("Rouvrir Collections (2e fois)", "clic", lambda: _cliquer(fen._title_bar.onglet(onglet)))
        yield ("ms", 1200)
        self.sentinelle.etape = "défilement soutenu de la galerie"
        page = fen._pages.page
        zone = _zone_defilante(page._pile.currentWidget()) if page is not None else None
        if zone is None:
            self.res["notes"].append("défilement soutenu : aucune zone à défiler")
            return
        arret = {"fini": False}
        sens = {"v": -1}

        def tourner():
            if arret["fini"]:
                return
            barre = zone.verticalScrollBar()
            if barre.value() >= barre.maximum():
                sens["v"] = 1
            elif barre.value() <= barre.minimum():
                sens["v"] = -1
            _molette(zone, sens["v"])
        from PyQt6.QtCore import QTimer
        minuteur = QTimer()
        minuteur.setInterval(16)
        minuteur.timeout.connect(tourner)
        minuteur.start()
        n_images = len(self.images)
        yield from self.cpu("défilement de la galerie", 5.0, note="molette toutes les 16 ms")
        arret["fini"] = True
        minuteur.stop()
        self.res.setdefault("animations_brutes", {})["défilement soutenu (galerie)"] = [self.images[n_images:]]
        yield from self.action("Revenir à la fiche (après le défilement)", "clic",
                               lambda: _cliquer(fen._title_bar.onglet(retour)))


class Pilote:
    """Fait avancer le parcours (un générateur) DANS la boucle d'événements."""

    def __init__(self, banc: Banc, gen) -> None:
        self.banc, self.gen = banc, gen
        self._limite = None

    def suivant(self, valeur=None) -> None:
        from PyQt6.QtCore import QTimer
        try:
            ordre = self.gen.send(valeur)
        except StopIteration:
            self.banc._ecrire()
            return
        except Exception as exc:
            import traceback
            self.banc.res["erreurs"].append(f"parcours : {exc!r} {traceback.format_exc()[-1500:]}")
            self.banc._ecrire()
            return
        genre, arg = ordre
        if genre == "ms":
            QTimer.singleShot(int(arg), self.suivant)
        elif genre == "reponse":
            self._reponse(arg)
        elif genre == "calme":
            self._calme(arg)

    def _reponse(self, apres: float) -> None:
        """Le dernier paint avant le premier battement à l'heure (≤ 8 ms de retard), 3 s au plus."""
        from PyQt6.QtCore import QTimer
        banc = self.banc
        etat = {"fin": None, "fini": False}
        limite = time.perf_counter() + 3.0

        def terminer():
            if not etat["fini"]:
                etat["fini"] = True
                banc._attente_paint = None
                banc._attente_battement = None
                QTimer.singleShot(0, lambda: self.suivant(etat["fin"]))

        def sur_paint(fin):
            etat["fin"] = fin
            banc.attendre_battement(sur_battement)

        def sur_battement(t, retard):
            if etat["fini"]:
                return
            if retard < 0.008 or t > limite:
                terminer()
            else:
                banc.attendre_paint(t, sur_paint)
        banc.attendre_paint(apres, sur_paint)
        QTimer.singleShot(3000, terminer)

    def _calme(self, t0: float) -> None:
        """La fin du dernier passage chargé (retard ≥ 16 ms) après t0, quand 150 ms se sont passées sans."""
        from PyQt6.QtCore import QTimer
        banc = self.banc
        limite = time.perf_counter() + 3.0

        def verifier():
            maintenant = time.perf_counter()
            charges = [t for t, _r in banc.battements if t >= t0]
            dernier = charges[-1] if charges else t0
            if maintenant - dernier >= 0.15 or maintenant > limite:
                self.suivant(dernier if charges else None)
            else:
                QTimer.singleShot(20, verifier)
        QTimer.singleShot(20, verifier)


def _cliquer(widget) -> None:
    """Un vrai clic (QTest) au centre du widget ; caché : `click()`."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    if widget is None:
        raise RuntimeError("rien à cliquer")
    if widget.isVisible():
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, widget.rect().center())
    else:
        widget.click()


def _zone_defilante(racine):
    from PyQt6.QtWidgets import QAbstractScrollArea
    if racine is None:
        return None
    zones = [z for z in racine.findChildren(QAbstractScrollArea)
             if z.isVisible() and z.verticalScrollBar().maximum() > 0]
    return max(zones, key=lambda z: z.verticalScrollBar().maximum(), default=None)


def _molette(zone, sens: int) -> None:
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtWidgets import QApplication
    vp = zone.viewport()
    centre = QPointF(vp.rect().center())
    ev = QWheelEvent(centre, QPointF(vp.mapToGlobal(centre.toPoint())), QPoint(0, 0), QPoint(0, 120 * sens),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(vp, ev)


if __name__ == "__main__":
    sys.exit(principal())
