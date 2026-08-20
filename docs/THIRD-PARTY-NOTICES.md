# Composants tiers

Accio Launcher est publié sous licence MIT (voir [LICENSE](LICENSE)). Le binaire
distribué `AccioLauncher.exe` embarque les composants ci-dessous, chacun soumis à
sa propre licence.

Ce fichier doit accompagner toute redistribution du binaire.

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

> **Décision retenue : code en MIT, binaire en GPL v3.**
>
> PyQt6 est distribué sous GPL v3. Un exécutable qui l'embarque est un travail
> dérivé, donc `AccioLauncher.exe` est redistribué sous GPL v3, laquelle exige
> que le code source correspondant reste disponible — il l'est, sur
> <https://github.com/ludvdber/AccioLauncher>.
>
> Le code source lui-même reste sous licence MIT. L'objectif est explicite :
> **n'importe qui doit pouvoir reprendre et réutiliser ce code**, y compris
> commercialement, à la seule condition de conserver la mention de copyright et
> donc de créditer ASTeam comme base du travail. La MIT étant compatible GPL,
> les deux coexistent sans conflit : seul l'exécutable assemblé porte la GPL v3.
>
> Concrètement, il suffit que la page de release et le site mentionnent que
> l'exécutable est couvert par la GPL v3, avec un lien vers le dépôt.

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

## Contenu des jeux

Accio Launcher **ne distribue aucun contenu de jeu**. Le launcher télécharge des
archives depuis des sources tierces référencées dans son catalogue ; les droits
sur les jeux Harry Potter appartiennent à Warner Bros. Interactive Entertainment,
Electronic Arts et leurs ayants droit respectifs.

Accio Launcher n'est ni affilié, ni approuvé, ni sponsorisé par Warner Bros.,
Electronic Arts ou J.K. Rowling.
