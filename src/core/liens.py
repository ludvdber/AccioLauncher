"""Adresses publiques du projet — une seule définition pour tout le launcher.

Le Discord n'était joignable que par Paramètres → À propos, et l'exe circule de
main en main : beaucoup de gens ne sont jamais passés par le site et
n'ouvriront pas les Paramètres pour découvrir qu'une communauté existe (Ludo,
2026-09-18). Il apparaît donc désormais à trois endroits — le bouton en haut à
droite de la fenêtre, le dialogue de plantage et l'avertissement « le jeu n'a
pas démarré » —, et trois copies d'une même adresse finissent par diverger le
jour où l'invitation change. Le Ko-fi et le site étaient déjà écrits en double
(`main_window`, `discord_presence`).

Module de `core` et non d'`ui` : la présence Discord, qui vit dans `core`,
affiche le site dans ses boutons.
"""

SITE_URL = "https://acciolauncher.be/"
DISCORD_URL = "https://discord.gg/TNwDQd7KGe"
KOFI_URL = "https://ko-fi.com/ludovic01"
