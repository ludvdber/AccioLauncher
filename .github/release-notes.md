<!-- Brouillon créé par le workflow « release ». Écrivez les nouveautés, puis « Publish release ».
     Ces lignes sont de l'INTERFACE : le launcher les affiche dans sa boîte de mise à
     jour. Pas d'emoji dans les titres (Windows les rend en couleur, hors palette), et
     des phrases courtes — douze lignes au plus arrivent à l'écran. -->

## Nouveautés

- Réglages par jeu bien plus complets (HP4 à HP7), en onglets, avec préréglages Légère, Équilibrée, Maximale.
- Bouton « ? » sur chaque réglage, et « Rétablir les réglages d'origine ».
- La fenêtre des réglages s'agrandit et se réduit.
- Limite à 144 images/s réellement atteinte sur HP4, HP5 et HP6.
- HP7 partie 1 limité à 60 images/s : ses cinématiques ne passent plus en accéléré.
- HP2 : manette PlayStation configurée (stick gauche pour Harry, stick droit pour la caméra).
- HP4 : emplacements de sauvegarde reconnus séparément.
- Composants manquants signalés avant le lancement (DirectX, Visual C++).
- Message clair quand Windows exige l'administrateur pour un jeu.
- Rapport de dépannage complet en un clic, prêt à coller sur Discord.
- Barre lumineuse de la manette éteinte à la fermeture.
- Linux : nombreuses corrections (installation après préparation de Wine, HP1, HP3, manette).

<!-- Le trait ci-dessous TERMINE les notes affichées dans le launcher :
     tout ce qui suit sert à lire la release sur GitHub et n'a rien à
     faire dans la boîte de mise à jour, qui explique déjà elle-même
     comment l'installation se fait. Ne pas le retirer. -->

---

## Télécharger

**Windows 10 et 11** — téléchargez **AccioLauncher.exe** ci-dessous et
lancez-le, aucune installation n'est nécessaire.

**Linux (Bazzite, Steam Deck, Fedora, Ubuntu…) — préversion** — téléchargez
**AccioLauncher-x86_64.AppImage**, rendez-le exécutable (clic droit →
Propriétés, ou `chmod +x`) et lancez-le. Les jeux tournent par Proton (via
`umu-run`) ou Wine : voir
[Linux / Bazzite](https://github.com/ludvdber/AccioLauncher#linux--bazzite).
Cette version Linux n'a pas encore été essayée sur une vraie machine : vos
retours sont les bienvenus sur le [Discord](https://discord.gg/TNwDQd7KGe).

Si vous avez déjà le launcher, il vous propose la mise à jour tout seul.

<details>
<summary><b>Vérifier que le fichier est l'original</b></summary>

<br>

Empreinte SHA-256 de `AccioLauncher.exe` :

```
{SHA256}
```

Pour la calculer sous Windows : `Get-FileHash .\AccioLauncher.exe -Algorithm SHA256`.

Ce fichier a été construit par GitHub Actions à partir du tag `{TAG}`, et
porte une attestation de provenance signée. Pour la vérifier avec
[GitHub CLI](https://cli.github.com/) :

```
gh attestation verify AccioLauncher.exe --repo ludvdber/AccioLauncher
```

Empreinte SHA-256 de `AccioLauncher-x86_64.AppImage` :

```
{SHA256_LINUX}
```

Sous Linux : `sha256sum AccioLauncher-x86_64.AppImage`, puis
`gh attestation verify AccioLauncher-x86_64.AppImage --repo ludvdber/AccioLauncher`.

</details>

---

<sub>Code source et exécutable sous GNU GPL v3, avec
[termes additionnels](https://github.com/ludvdber/AccioLauncher/blob/{TAG}/ADDITIONAL-TERMS.md).
Composants tiers :
[THIRD-PARTY-NOTICES](https://github.com/ludvdber/AccioLauncher/blob/{TAG}/docs/THIRD-PARTY-NOTICES.md).</sub>
