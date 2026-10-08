# Avant une release : l'essai en jeu

Les tests automatiques ne lancent aucun vrai jeu. Cet essai, si : il joue chaque jeu **depuis la vraie fenêtre du launcher** (bouton JOUER), puis rend un verdict point par point. À faire avant toute release qui touche au lancement, à la surveillance du processus (`process_monitor.py`, `game_session.py`), au catalogue ou aux DLL du correctif. Pas pour une release qui ne change que des textes.

## Ce qu'il faut

- **Le « oui » de Ludo pour la session.** L'essai prend la souris et le clavier : le PC doit être libre pendant environ 15 minutes pour les six jeux. Le pilote refuse de partir sans `ACCIO_OUI=1`.
- **Jamais HP7 ni HP8** (HP8 fige tous les cœurs). L'essai ne couvre que HP1 à HP6.
- Le son du jeu est coupé tout seul (`son.py`). Après un plantage du pilote : `python son.py retablir`, jeu relancé.

## Les six lancements

Le pilote vit dans l'atelier, hors dépôt : `C:\Users\User\Tools\accio_fix_atelier\essai_avant_release.py`. Un lancement par jeu :

```text
set ACCIO_OUI=1
python essai_avant_release.py hp1 v1.1.6
python essai_avant_release.py hp2 v1.1.6
... jusqu'à hp6
```

| Jeu | Ce que le pilote fait | Ce qui est vérifié |
|---|---|---|
| HP1 | attend le menu, Alt+Entrée ×2, Alt+Tab | fenêtre en moins de 60 s, le jeu survit à Alt+Tab, grâce de relance gardée |
| HP2 | boîte de démarrage, « Charger partie », emplacement 1, Alt+Entrée ×2, Alt+Tab | idem, et la relance de l'assistant ne ferme pas la session |
| HP3 | menu pendant 45 s, Alt+Tab | fenêtre, survie à Alt+Tab, retour sans attendre 10 s |
| HP4, HP5, HP6 | menus scriptés, F8 (avant/après du correctif), banc F11 de 30 s, Alt+Tab | fenêtre, survie à Alt+Tab, retour sans attendre 10 s |

Pour tous : fermeture propre (WM_CLOSE, sans tuer le jeu), le launcher revient à l'écran, la barre du bas dit « partie terminée », aucune écriture de registre demandée. Le pilote remet ensuite à l'octet ce qu'il a touché (dossier du jeu, `_Launcher`, Documents de HP1 à HP3) et garde les sauvegardes avant/après.

## Lire le résultat

Les preuves sont dans `essais_release\<étiquette>\` : `journal.txt` (dernière ligne : `VERDICT HPx : n/m points`), captures, `launcher.log`, bancs F11. Le code de sortie est 1 s'il y a un échec. **Un seul ÉCHEC bloque la release** tant qu'il n'est pas expliqué.

Le point « n'attendent plus 10 s » mesure ACT-049 : HP3 à HP6 doivent rendre la main en moins de 6 s, HP1 et HP2 garder leur grâce d'au moins 8 s (`relance` au catalogue).
