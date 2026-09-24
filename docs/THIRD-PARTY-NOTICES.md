# Composants tiers

Accio Launcher est publié sous GNU GPL v3 uniquement, avec des termes additionnels
(voir [LICENSE](../LICENSE) et [ADDITIONAL-TERMS.md](../ADDITIONAL-TERMS.md)). Les
binaires distribués — `AccioLauncher.exe` pour Windows,
`AccioLauncher-x86_64.AppImage` pour Linux — embarquent les composants
ci-dessous, chacun soumis à sa propre licence.

Ce fichier doit accompagner toute redistribution des binaires.

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

## 7-Zip 26.00 pour Linux (`7zzs`) — Igor Pavlov

Fichier : `assets/7z/linux/7zzs` (build Linux uniquement : `accio_launcher.spec`
l'écarte de l'exe Windows, comme il écarte `7z.exe` du build Linux)
Licence : GNU LGPL v2.1+, avec restriction unRAR et portions BSD 2/3-clause
Texte complet : **[`assets/7z/linux/License.txt`](assets/7z/linux/License.txt)**
(copie verbatim de l'archive officielle)
Site : <https://7-zip.org>

Provenance : `7z2600-linux-x64.tar.xz`, publié par l'auteur sur
<https://www.7-zip.org/download.html> et sur son dépôt officiel
<https://github.com/ip7z/7zip/releases/tag/26.00>.

| Fichier | SHA-256 |
|---|---|
| `7z2600-linux-x64.tar.xz` (archive d'origine) | `c74dc4a48492cde43f5fec10d53fb2a66f520e4a62a69d630c44cb22c477edc6` |
| `7zzs` | `4836193a032a410c3e0f3c177705ed4da51d4bfb396263add6b2d68d79cd518a` |
| `License.txt` | `1790374e5352329cedb46ee3808930a88e9ca2f08b82b10fcf5cf605d2c301b1` |

`7zzs` est la variante **liée statiquement** de l'archive : elle ne dépend
d'aucune bibliothèque du système, donc tourne à l'identique sur Bazzite, sur
une Debian ancienne ou dans le Steam Linux Runtime. Même usage que sous
Windows : décompression 7z et zip, jamais RAR. La même obligation de
reproduire `License.txt` s'applique : il voyage avec le binaire.

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

Fichiers : bibliothèques `Qt6*.dll` (Windows) et `libQt6*.so.6` (Linux)
embarquées par PyQt6, avec ce que le paquet PyQt6-Qt6 livre à côté : FFmpeg
(`avcodec`, `avformat`, `avutil`, `swresample`, `swscale` — GNU LGPL v2.1+) et,
sous Linux, ICU (`libicu*` — licence Unicode)
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

## Runtime AppImage (`type2-runtime`) — projet AppImage

Fichier : l'en-tête exécutable de `AccioLauncher-x86_64.AppImage` (Linux)
Version : `20251108`, SHA-256
`2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d`
Licence : MIT
Source : <https://github.com/AppImage/type2-runtime/tree/20251108>

Le runtime est la partie de toute AppImage qui monte l'image et lance le
programme. Il est lié **statiquement** à :

| Composant | Licence |
|---|---|
| libfuse 3.15.0 | GNU LGPL v2.1+ (bibliothèque) |
| squashfuse 0.5.2 | BSD 2-clause |
| zstd | BSD 3-clause (ou GPL v2) |
| zlib | licence zlib |
| mimalloc | MIT |
| musl libc | MIT |

Les sources du runtime et ses scripts de construction (qui téléchargent et
vérifient libfuse et squashfuse par empreinte) sont publics à l'adresse
ci-dessus : c'est ce qui permet, comme l'exige la LGPL pour une liaison
statique, de le reconstruire avec une libfuse modifiée.

---

## appimagetool — projet AppImage

Version : `1.9.1`, SHA-256
`ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`
Licence : MIT
Source : <https://github.com/AppImage/appimagetool/tree/1.9.1>

Outil de CONSTRUCTION : il assemble l'AppImage (`build/linux/appimage.py`) et
n'est pas distribué avec elle. Cité pour la provenance du fichier publié.

---

## Bibliothèques système embarquées dans l'AppImage (Linux)

PyInstaller copie dans l'AppImage les bibliothèques de la machine de build
(Ubuntu 22.04) dont dépendent Python et Qt, sauf celles que toute machine
fournit (liste d'exclusion AppImage, `build/linux/dependances.py`). Toutes
sont utilisées sans modification et liées dynamiquement :

| Bibliothèques | Licence |
|---|---|
| OpenSSL 3 (`libssl`, `libcrypto`) | Apache 2.0 |
| GLib (`libglib-2.0`, `libgthread-2.0`), libsndfile, mpg123, PulseAudio (client), libsystemd, libgcrypt, libapparmor, libasyncns, keyutils | GNU LGPL v2.1+ |
| LAME (`libmp3lame`) | GNU LGPL v2+ |
| D-Bus (`libdbus-1`) | AFL 2.1 ou GNU GPL v2+ |
| X11 et XCB (`libXext`, `libXrandr`, `libXrender`, `libxcb-*`), libxkbcommon, libffi, MIT Kerberos (`libkrb5`, `libgssapi_krb5`, `libk5crypto`) | MIT / X11 |
| FLAC, Ogg, Vorbis, Opus, zstd, PCRE2 | BSD 3-clause |
| lz4, libcap | BSD 2-clause |
| Brotli | MIT |
| XZ (`liblzma`) | 0BSD / domaine public |
| bzip2 | licence bzip2 (BSD) |

Le code source de chacune est disponible dans les dépôts d'Ubuntu 22.04
(`apt source <paquet>`), et sur le site de chaque projet.

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
