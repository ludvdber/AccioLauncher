# Composants tiers

Accio Launcher est publié sous GNU GPL v3 uniquement, avec des termes additionnels
(voir [LICENSE](../LICENSE) et [ADDITIONAL-TERMS.md](../ADDITIONAL-TERMS.md)). Le binaire
distribué `AccioLauncher.exe` embarque les composants ci-dessous, chacun soumis à
sa propre licence.

Ce fichier doit accompagner toute redistribution du binaire.

Le nom et le logo d'Accio Launcher ne relèvent d'aucune de ces licences :
voir [TRADEMARKS.md](../TRADEMARKS.md).

---

## 7-Zip 26.00 — Igor Pavlov

Fichiers : `assets/7z/7z.exe`, `assets/7z/7z.dll`
Licence : GNU LGPL v2.1+, avec restriction unRAR et portions BSD 2/3-clause
Texte complet : **[`assets/7z/License.txt`](assets/7z/License.txt)** (copie verbatim
de la distribution officielle 7-Zip 26.00)
Site : <https://7-zip.org>

> « Redistributions in binary form must reproduce related license information from
> this file. »

C'est la raison d'être de `assets/7z/License.txt` : le fichier est embarqué dans
l'exécutable au même titre que les binaires 7-Zip, et ne doit pas être retiré du
dossier `assets/`.

7-Zip est utilisé tel quel, sans modification du code source. Accio Launcher
n'utilise que la décompression 7z et zip — jamais le moteur RAR.

---

## PyQt6 — Riverbank Computing

Licence : **GNU GPL v3** (ou licence commerciale Riverbank)
Site : <https://riverbankcomputing.com/software/pyqt/>

> **Décision retenue (2026-09-24) : code ET binaire en GPL v3 uniquement, avec
> termes additionnels.**
>
> PyQt6 est distribué sous GPL v3. Un exécutable qui l'embarque est un travail
> dérivé, donc `AccioLauncher.exe` est redistribué sous GPL v3, laquelle exige
> que le code source correspondant reste disponible — il l'est, sur
> <https://github.com/ludvdber/AccioLauncher>.
>
> Le code était sous MIT jusqu'à la 1.0.6. Il passe sous GPL v3 pour que
> **personne ne puisse en tirer une version fermée** : quiconque redistribue
> doit publier ses sources sous la même licence. C'est la licence la plus
> stricte que permet PyQt6 : interdire la redistribution exigerait une licence
> commerciale Riverbank ou le passage à PySide6 (LGPL). Les termes additionnels
> (article 7 : attribution, origine, publicité, marque) sont dans
> [ADDITIONAL-TERMS.md](../ADDITIONAL-TERMS.md).

---

## Qt 6 — The Qt Company

Fichiers : bibliothèques `Qt6*.dll` embarquées par PyQt6
Licence : GNU LGPL v3 (ou licence commerciale)
Site : <https://www.qt.io>

Qt est utilisé sans modification, via PyQt6, et lié dynamiquement — la forme
d'utilisation prévue par la LGPL v3.

---

## httpx — Encode OSS Ltd.

Licence : BSD 3-clause
Site : <https://www.python-httpx.org>

Utilisé pour le téléchargement des archives de jeux et les vérifications de mise
à jour.

---

## CPython — Python Software Foundation

Licence : PSF License Agreement (compatible GPL)
Site : <https://python.org>

L'interpréteur et la bibliothèque standard sont embarqués par PyInstaller.

---

## PyInstaller — PyInstaller Development Team

Licence : GNU GPL v2+, **avec exception bootloader**
Site : <https://pyinstaller.org>

L'exception attachée au bootloader autorise explicitement la distribution de
l'application gelée sous les termes que son auteur choisit. PyInstaller n'impose
donc aucune contrainte propre sur `AccioLauncher.exe`.

---

## Cinzel & Cinzel Decorative — Natanael Gama

Fichiers : `assets/fonts/Cinzel-Variable.ttf`,
`assets/fonts/CinzelDecorative-{Regular,Bold,Black}.ttf`
Licence : SIL Open Font License 1.1
Texte : <https://openfontlicense.org>
Source : <https://fonts.google.com/specimen/Cinzel>

Polices utilisées sans modification. L'OFL autorise la redistribution embarquée
dans un logiciel, y compris commercial, à condition que les polices ne soient pas
vendues seules et que la licence accompagne la distribution.

---

## Gelasio — Eben Sorkin (Sorkin Type)

Fichier : `assets/fonts/Gelasio-Variable.ttf`
Licence : SIL Open Font License 1.1
Texte complet : **[`assets/fonts/Gelasio-OFL.txt`](assets/fonts/Gelasio-OFL.txt)**
(copie verbatim de la distribution officielle)
Source : <https://fonts.google.com/specimen/Gelasio> · <https://github.com/SorkinType/Gelasio>

Police de corps (descriptions, notes, toasts), utilisée sans modification.
Gelasio est **métriquement compatible avec Georgia** : elle la remplace sans
déplacer un seul retour à la ligne, tout en étant librement redistribuable — ce
que Georgia, police Microsoft, n'est pas. C'est aussi ce qui rend l'interface
identique sous Linux, où Georgia n'existe pas.

---

## Phosphor Icons — Helena Zhang & Tobias Fried

Fichiers : `assets/icons/phosphor/*.svg` (paquet `@phosphor-icons/core` 2.1.1,
graisse Bold ; lecture et pause en graisse Fill)
Licence : MIT
Texte complet : **[`assets/icons/phosphor/LICENSE.txt`](assets/icons/phosphor/LICENSE.txt)**
(copie verbatim du paquet)
Source : <https://phosphoricons.com> · <https://github.com/phosphor-icons/core>

Pictogrammes de l'interface (réglages, statistiques, site, lecteur vidéo),
utilisés sans modification : la couleur est appliquée au rendu, les fichiers
sont ceux du paquet à l'octet près. La MIT exige que sa mention accompagne
toute copie, d'où la licence placée à côté des fichiers, dans l'exécutable.

---

## Logos Discord et Ko-fi — marques de leurs propriétaires

**Discord** — `assets/icons/marques/Discord-Symbol-White.svg` et
`Discord-Symbol-Blurple.svg`, fichiers du kit de marque officiel
(<https://discord.com/branding>), inchangés. Discord est une marque de
Discord Inc. Conformément à ses règles, le logo n'est ni modifié, ni déformé,
ni recoloré : il est blanc au repos et Blurple au survol, ses deux versions
officielles.

**Ko-fi** — `assets/icons/marques/kofi.svg`, tracé publié par
[Simple Icons](https://simpleicons.org) 16.31.0 (projet sous CC0 1.0), relevé
par eux sur le kit de marque de Ko-fi (<https://more.ko-fi.com/brand-assets>).
Ko-fi est une marque de Ko-fi Labs Limited. CC0 couvre le fichier, pas la
marque : le logo est utilisé sans déformation, pour renvoyer vers la page
Ko-fi du projet, ce à quoi il est destiné.

Accio Launcher n'est ni affilié, ni approuvé, ni sponsorisé par Discord ou
Ko-fi.

---

## Contenu des jeux

Accio Launcher **ne distribue aucun contenu de jeu**. Le launcher télécharge des
archives depuis des sources tierces référencées dans son catalogue ; les droits
sur les jeux Harry Potter appartiennent à Warner Bros. Interactive Entertainment,
Electronic Arts et leurs ayants droit respectifs.

Accio Launcher n'est ni affilié, ni approuvé, ni sponsorisé par Warner Bros.,
Electronic Arts ou J.K. Rowling.
