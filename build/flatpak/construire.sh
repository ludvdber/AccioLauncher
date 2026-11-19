#!/bin/sh
# Construit le Flatpak d'Accio Launcher depuis le dossier gelé de PyInstaller.
#
#   1. archive reproductible (preparer.py) ;
#   2. flatpak-builder (runtime org.freedesktop.Platform 25.08) dans un dépôt local ;
#   3. bundle installable : dist/AccioLauncher.flatpak.
#
# Prérequis : dist/AccioLauncher (PyInstaller), flatpak et flatpak-builder,
# le runtime et le SDK 25.08 de Flathub (`flatpak install flathub
# org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08`), Pillow pour les
# icônes. Le PY d'ACCIO_PY, sinon python3.
set -eu
ICI="$(cd "$(dirname "$0")" && pwd)"
RACINE="$(cd "$ICI/../.." && pwd)"
PY="${ACCIO_PY:-python3}"

echec() { echo "ERREUR : $1" >&2; exit 1; }
command -v flatpak-builder >/dev/null 2>&1 || echec "flatpak-builder introuvable."

echo "[1/3] Archive du dossier gelé..."
"$PY" "$ICI/preparer.py" || echec "archive impossible."

echo "[2/3] flatpak-builder..."
TRAVAIL="$RACINE/build/flatpak-travail"
flatpak-builder --force-clean --disable-rofiles-fuse --repo="$TRAVAIL/depot" \
    --state-dir="$TRAVAIL/etat" "$TRAVAIL/app" \
    "$ICI/be.acciolauncher.AccioLauncher.json" || echec "flatpak-builder a échoué."

echo "[3/3] Bundle..."
mkdir -p "$RACINE/dist"
flatpak build-bundle --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
    "$TRAVAIL/depot" "$RACINE/dist/AccioLauncher.flatpak" be.acciolauncher.AccioLauncher \
    || echec "bundle impossible."
echo "Flatpak : dist/AccioLauncher.flatpak"
echo "Installer : flatpak install --user dist/AccioLauncher.flatpak"
