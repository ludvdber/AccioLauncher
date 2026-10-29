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
# Salon #accio-medias, où « Partager sur Discord » de la galerie mène tout droit
# (Ludo, 2026-10-22) : l'invitation ne faisait qu'ouvrir le serveur, et il
# fallait encore trouver le salon. Serveur ASTeam, identifiant lu sur l'invitation.
DISCORD_MEDIAS_URL = "https://discord.com/channels/155745867779801090/1560367010008014991"
KOFI_URL = "https://ko-fi.com/ludovic01"
# Le dépôt porte le code source ET la licence : la GPL v3 et ses termes
# additionnels exigent qu'on sache où les trouver (voir ADDITIONAL-TERMS.md).
DEPOT_URL = "https://github.com/ludvdber/AccioLauncher"
# Le catalogue des jeux et les releases qui portent leurs archives. Constantes
# d'ici et JAMAIS relues du catalogue lui-même (audit du 2026-10-29) : un
# catalogue compromis une seule fois y aurait écrit sa propre adresse, et tous
# les launchers auraient suivi la sienne pour toujours, empreintes comprises.
DEPOT_JEUX = "ludvdber/accio-launcher-games"
CATALOGUE_URL = f"https://raw.githubusercontent.com/{DEPOT_JEUX}/main/games.json"
RELEASES_JEUX_API = f"https://api.github.com/repos/{DEPOT_JEUX}/releases?per_page=100"
# Notes de chaque version du launcher, ouvertes par le numéro de version dans
# À propos. La LISTE et non le tag courant : un exe lancé avant la publication
# de sa release (essais, build locale) mènerait sinon à une page 404.
NOTES_VERSIONS_URL = f"{DEPOT_URL}/releases"
# Dernière version publiée : repli de l'avis de mise à jour quand la réponse de
# GitHub ne porte pas d'adresse sûre (`updater`).
DERNIERE_VERSION_URL = f"{DEPOT_URL}/releases/latest"
# Nouveau signalement, pré-rempli par le dialogue de plantage.
SIGNALER_URL = f"{DEPOT_URL}/issues/new"
# Section « Linux / Bazzite » du README : quoi installer quand ni umu-run ni
# wine ne sont trouvés. Une ancre de titre GitHub : « Linux / Bazzite » donne
# `linux--bazzite` (minuscules, espaces en tirets, barre oblique retirée).
GUIDE_LINUX_URL = f"{DEPOT_URL}#linux--bazzite"
# « Protection contre les virus et menaces » de Sécurité Windows, ouverte par
# l'aide antivirus de la fiche (Windows seulement : le bouton n'existe pas ailleurs).
SECURITE_WINDOWS_URL = "windowsdefender://threatsettings/"
