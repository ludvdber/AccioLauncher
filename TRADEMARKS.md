# Le nom et le logo d'Accio Launcher

Le code d'Accio Launcher est libre. Son nom et son logo ne le sont pas : ils
désignent **le** projet officiel, et les joueurs doivent pouvoir le
reconnaître. Cette page dit ce que vous pouvez en faire.

## Ce qui est concerné

- le nom **Accio Launcher** ;
- le logo et l'icône : `assets/accio_launcher.ico`, `assets/accio_launcher.png`,
  `assets/accio_logo_horizontal.png`, et l'image de partage
  `docs/social_preview.png`.

## Ce que vous pouvez faire sans demander

- Forker le dépôt, modifier le code et utiliser votre version pour vous, sous
  son nom et avec son logo d'origine.
- Parler du projet sous son nom : article, vidéo, tutoriel, capture d'écran.
- Présenter un projet dérivé comme « basé sur Accio Launcher », avec un lien
  vers ce dépôt.

## Ce qui demande une autorisation écrite

- Distribuer une version modifiée sous le nom Accio Launcher, ou avec son logo
  ou son icône.
- Utiliser le nom ou le logo pour un autre logiciel, un site, un serveur
  Discord ou une chaîne, d'une façon qui laisse croire à un lien avec le projet
  officiel.

Pour demander : sur le [Discord](https://discord.gg/TNwDQd7KGe), ou dans une
[issue](https://github.com/ludvdber/AccioLauncher/issues).

## Publier votre propre version

1. Donnez-lui un autre nom.
2. Remplacez le logo et l'icône (les fichiers listés plus haut).
3. Indiquez clairement qu'il ne s'agit pas du projet officiel.
4. Changez les adresses du projet, sans quoi le launcher officiel
   remplacerait votre version à sa première mise à jour, et vos utilisateurs
   atterriraient sur son Discord : `src/core/updater.py` (releases),
   `src/core/liens.py` (site, Discord, Ko-fi) et `src/ui/crash_dialog.py`
   (issues).

## Et les licences ?

Le code source et l'exécutable sont sous GNU GPL v3, avec des
[termes additionnels](ADDITIONAL-TERMS.md). Cette licence porte sur le
**droit d'auteur** : elle n'accorde aucun droit sur le nom ni sur le logo
**en tant que marque**, condition prévue par la GPL v3 elle-même
(article 7, point e).

---

<details>
<summary><b>English</b></summary>

<br>

The Accio Launcher code is free software; its name and logo are not. They
identify the official project.

**Covered:** the name *Accio Launcher*, the logo and the icon
(`assets/accio_launcher.ico`, `assets/accio_launcher.png`,
`assets/accio_logo_horizontal.png`, `docs/social_preview.png`).

**Allowed without asking:** forking, modifying and using your copy yourself;
referring to the project by name (articles, videos, tutorials); describing a
derived project as "based on Accio Launcher" with a link to this repository.

**Needs written permission:** distributing a modified version under the
Accio Launcher name or with its logo or icon; using the name or logo for
another product, website, Discord server or channel in a way that suggests an
official connection.

**Publishing your own version:** give it another name, replace the logo and
icon, state that it is not the official project, and change the project URLs
(`src/core/updater.py`, `src/core/liens.py`, `src/ui/crash_dialog.py`),
otherwise the official launcher would replace your version on its first
update.

The source code and the executable are under GNU GPL v3, with
[additional terms](ADDITIONAL-TERMS.md). It covers copyright and grants no
trademark rights to the name or logo, an additional term permitted by GPL v3
section 7(e).

</details>
