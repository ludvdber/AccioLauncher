#!/bin/sh
# Build Linux : icône -> lint -> tests -> géométrie -> PyInstaller -> AppImage.
#
# Le pendant de build.bat, avec la même règle : on s'ARRÊTE au premier échec.
# Une AppImage publiée avec une régression coûte plus cher que deux minutes
# d'attente. Sortie : dist/AccioLauncher-x86_64.AppImage.
#
# Sur un poste (Bazzite compris), lancé hors d'un environnement virtuel, il
# s'en crée un (.venv-build) : le Python d'un système atomique ne se modifie
# pas, et pip y refuserait d'installer quoi que ce soit. En intégration
# continue, ACCIO_PY désigne l'interpréteur installé par le workflow.
set -eu
cd "$(dirname "$0")"

echec() {
    echo "ERREUR : $1" >&2
    exit 1
}

# Préfère 3.14, puis 3.13, puis 3.12 — le plancher réel (pyproject >=3.12).
if [ -n "${ACCIO_PY:-}" ]; then
    PY="$ACCIO_PY"
else
    PY=""
    for candidat in python3.14 python3.13 python3.12 python3; do
        if command -v "$candidat" >/dev/null 2>&1 \
            && "$candidat" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
            PY="$candidat"
            break
        fi
    done
    [ -n "$PY" ] || echec "aucun Python 3.12+ trouvé."
    if ! "$PY" -c 'import sys; sys.exit(sys.prefix == sys.base_prefix)'; then
        if [ ! -x .venv-build/bin/python ]; then
            echo "Création de l'environnement de build (.venv-build)..."
            "$PY" -m venv .venv-build || echec "création de .venv-build impossible."
        fi
        PY="$(pwd)/.venv-build/bin/python"
    fi
fi

echo "=== Accio Launcher - Build Linux ==="
"$PY" --version
echo

echo "Installation des dépendances de build..."
"$PY" -m pip install -r requirements-dev.txt --quiet || echec "installation des dépendances échouée."
echo

# L'icône n'est pas générée : c'est un asset dessiné (7 tailles), vérifié ici.
# L'AppImage en extrait chaque taille telle quelle.
echo "[1/6] Vérification de l'icône..."
"$PY" build/create_icon.py || echec "icône manquante ou illisible."

echo "[2/6] Lint..."
"$PY" -m ruff check . || echec "lint échoué - build interrompu."

echo "[3/6] Tests..."
"$PY" -m pytest -q || echec "tests en échec - build interrompu."

# Mêmes contrôles de mise en page que la suite, mais avec les VRAIES polices :
# sous offscreen, Qt n'en voit aucune (voir tools/audit_geometrie.py). Il faut
# donc un affichage ; sans session graphique (intégration continue), Xvfb en
# tient lieu.
echo "[4/6] Géométrie avec les vraies polices..."
if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    "$PY" tools/audit_geometrie.py || echec "anomalie de mise en page - build interrompu."
elif command -v xvfb-run >/dev/null 2>&1; then
    xvfb-run -a -s "-screen 0 1920x1080x24" "$PY" tools/audit_geometrie.py \
        || echec "anomalie de mise en page - build interrompu."
else
    echec "ni session graphique ni xvfb-run : installer Xvfb (paquet xvfb) pour l'audit de géométrie."
fi

echo "[5/6] Build PyInstaller..."
"$PY" -m PyInstaller accio_launcher.spec --noconfirm || echec "build PyInstaller échoué."

echo "[6/6] AppImage..."
"$PY" build/linux/appimage.py || echec "construction de l'AppImage échouée."

echo
echo "=== Build terminé ! ==="
echo "AppImage : dist/AccioLauncher-x86_64.AppImage"
