<div align="center">

# ⚡ Accio Launcher

### Le launcher magique pour les jeux Harry Potter PC

[![Version](https://img.shields.io/badge/version-1.0.0-d4a017?style=for-the-badge&labelColor=0d0d1a)](https://github.com/ludvdber/AccioLauncher/releases)
[![Python](https://img.shields.io/badge/Python-3.12+-3776ab?style=for-the-badge&logo=python&logoColor=white&labelColor=0d0d1a)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.10-41cd52?style=for-the-badge&labelColor=0d0d1a)](https://pypi.org/project/PyQt6/)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078d4?style=for-the-badge&logo=windows11&logoColor=white&labelColor=0d0d1a)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-MIT-e74c3c?style=for-the-badge&labelColor=0d0d1a)](LICENSE)

*Je jure solennellement que mes intentions sont mauvaises.* 🗺️

[**⬇ Télécharger**](https://github.com/ludvdber/AccioLauncher/releases) · [🐛 Signaler un bug](https://github.com/ludvdber/AccioLauncher/issues) · [💡 Demander une feature](https://github.com/ludvdber/AccioLauncher/issues/new)

</div>

---

<div align="center">
  <img src="docs/social_preview.png" width="800" alt="Accio Launcher — Aperçu">
</div>

---

## ✨ Fonctionnalités

| | |
|---|---|
| 🎮 **6 jeux Harry Potter PC** | De l'École des Sorciers (2001) au Prince de Sang-Mêlé (2009) |
| ⬇️ **Téléchargement en un clic** | Téléchargement, extraction 7z et installation automatiques |
| 🎨 **UI immersive style AAA** | Particules magiques, parallaxe, transitions cinématiques, glow doré |
| 📺 **Trailers vidéo** | Vidéos de présentation en arrière-plan avec contrôle du volume |
| 🔄 **Versioning et changelog** | Suivi des versions avec historique détaillé des changements |
| 📥 **System tray intelligent** | Se minimise pendant le jeu, se restaure automatiquement |
| ⚙️ **Paramètres intégrés** | Dossier d'installation, gestion de l'espace disque, préférences |
| 🛡️ **Code audité** | HTTPS only, anti path-traversal, Zip Slip prevention, thread safety |

---

## 🎮 Jeux supportés

| # | Jeu | Année | Développeur | Taille |
|:-:|-----|:-----:|:-----------:|:------:|
| I | Harry Potter à l'École des Sorciers | 2001 | KnowWonder | ~1.2 Go |
| II | Harry Potter et la Chambre des Secrets | 2002 | KnowWonder | ~2.5 Go |
| III | Harry Potter et le Prisonnier d'Azkaban | 2004 | KnowWonder | ~2.8 Go |
| IV | Harry Potter et la Coupe de Feu | 2005 | EA UK | ~3.5 Go |
| V | Harry Potter et l'Ordre du Phénix | 2007 | EA UK | ~4.2 Go |
| VI | Harry Potter et le Prince de Sang-Mêlé | 2009 | EA UK | ~4.5 Go |

> *Harry Potter et les Reliques de la Mort (Parties I & II) et Coupe du Monde de Quidditch arrivent dans une future mise à jour.*

---

## 🚀 Installation

### 💎 Méthode simple

1. Téléchargez **AccioLauncher.exe** depuis les [Releases](https://github.com/ludvdber/AccioLauncher/releases)
2. Lancez l'exécutable
3. Choisissez votre dossier d'installation
4. Sélectionnez un jeu et cliquez sur **Télécharger** ⚡

### 🧙 Méthode développeur

```bash
git clone https://github.com/ludvdber/AccioLauncher.git
cd AccioLauncher
pip install -r requirements.txt
python main.py
```

> **Prérequis :** Python 3.12+, Windows 10/11

<details>
<summary><b>📦 Builder l'exécutable</b></summary>

```bash
pip install -r requirements-dev.txt
build.bat
# → dist/AccioLauncher.exe
```

</details>

---

## 📸 Captures d'écran

<div align="center">
  <img src="docs/screenshot.png" width="800" alt="Accio Launcher — Vue principale">
  <br>
  <sub><i>Vue principale — carrousel, particules magiques et effets de parallaxe</i></sub>
  <br><br>
  <table>
    <tr>
      <td><img src="docs/screen_installed.png" width="400" alt="Jeu installé avec vidéo"></td>
      <td><img src="docs/screen_changelog.png" width="400" alt="Versions et changelog"></td>
    </tr>
    <tr>
      <td align="center"><sub>Jeu installé — vidéo en fond et contrôle audio</sub></td>
      <td align="center"><sub>Gestion des versions et changelog</sub></td>
    </tr>
  </table>
</div>

---

## 🛠️ Stack technique

| Composant | Technologie |
|-----------|------------|
| **Langage** | Python 3.12+ avec type hints modernes |
| **Interface** | PyQt6 — widgets custom, QPainter, QPropertyAnimation |
| **Téléchargement** | httpx — streaming HTTPS avec suivi de progression |
| **Extraction** | py7zr — support archives 7z et zip |
| **Effets visuels** | Particules, parallaxe, glow, transitions — tout en QPainter natif |
| **Architecture** | Séparation `core/` (logique métier) et `ui/` (interface) |
| **Packaging** | PyInstaller — exécutable unique Windows |

---

## 🗺️ Roadmap

- [x] **V1** — Launcher + carrousel + téléchargement + system tray + versioning
- [ ] **V2** — Configuration graphique intégrée (DGVoodoo, résolution, compatibilité)
- [ ] **V3** — Patches et corrections de bugs spécifiques aux jeux
- [ ] **V4** — Support Linux (Wine / Proton)
- [ ] **V5** — Internationalisation FR / EN

---

## 🤝 Contribution

Les contributions sont les bienvenues !

- 🐛 **Bug ?** → Ouvrez une [Issue](https://github.com/ludvdber/AccioLauncher/issues)
- 💡 **Idée ?** → Proposez une [Feature Request](https://github.com/ludvdber/AccioLauncher/issues/new)
- 🔧 **Code ?** → Forkez, créez une branche, soumettez une PR

---

## ⚖️ Avertissement légal

Accio Launcher est un outil de gestion et de lancement de jeux. **Aucun fichier de jeu n'est inclus dans le launcher.** 

L'utilisation de ce logiciel implique que vous possédez une copie légale des jeux que vous installez via le launcher. Il est de votre entière responsabilité de vous assurer que vous disposez des droits nécessaires pour utiliser ces jeux dans votre juridiction.

Les jeux Harry Potter sont la propriété intellectuelle de Warner Bros. Entertainment Inc. et Electronic Arts Inc. Ce projet n'est ni affilié, ni approuvé, ni sponsorisé par ces entreprises.

Le développeur d'Accio Launcher ne peut être tenu responsable de l'utilisation qui est faite de ce logiciel par ses utilisateurs. Ce projet est fourni "tel quel", sans garantie d'aucune sorte.

---

<div align="center">

Fait avec 🪄 et beaucoup de ☕

*Méfait accompli.* 🗺️

</div>

---

<details>
<summary><b>🇬🇧 English</b></summary>

<br>

### Accio Launcher

A magical desktop launcher for Harry Potter PC games (2001–2009). Features one-click download & install, immersive AAA-style UI with particles, parallax and cinematic transitions, video backgrounds, version tracking with changelog, smart system tray minimization during gameplay, and security-audited code.

**Quick start:** Download `AccioLauncher.exe` from [Releases](https://github.com/ludvdber/AccioLauncher/releases), run it, pick your install folder, and you're ready to play.

**Dev setup:** `git clone` → `pip install -r requirements.txt` → `python main.py`

Built with Python 3.12+, PyQt6, httpx, and py7zr. Windows 10/11 only (Linux support planned).

</details>
