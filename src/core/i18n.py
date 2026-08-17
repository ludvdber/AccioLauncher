"""Internationalisation minimaliste FR ↔ EN — sans dépendance Qt.

Le français est la langue source : les chaînes du code SONT les clés.
`tr("…")` renvoie la traduction anglaise si la langue active est "en",
sinon la clé telle quelle. Une chaîne absente du dictionnaire reste donc
en français — la couverture est incrémentale et ne casse jamais l'UI.

Les chaînes paramétrées utilisent des gabarits `{}` : `tr("Version {}").format(x)`.
Changer de langue nécessite un redémarrage (les chaînes sont posées à la
construction des widgets) — l'UI le précise.
"""

_lang = "fr"


def set_language(lang: str) -> None:
    """Langue active : "fr" (défaut) ou "en"."""
    global _lang
    _lang = lang if lang in ("fr", "en") else "fr"


def get_language() -> str:
    return _lang


def tr(text: str) -> str:
    """Traduit une chaîne source française vers la langue active."""
    if _lang == "fr":
        return text
    return _EN.get(text, text)


_EN: dict[str, str] = {
    # ── Unités de taille / vitesse (format_size / format_bytes / format_speed) ──
    "Go": "GB",
    "Mo": "MB",
    "Ko/s": "KB/s",
    "Mo/s": "MB/s",
    # ── Settings ──
    "Paramètres": "Settings",
    "⚙ Paramètres": "⚙ Settings",
    "Dossier d'installation": "Install folder",
    "Ouvrir": "Open",
    "Changer…": "Change…",
    "Changer le dossier d'installation": "Change install folder",
    "Espace libre : {}": "Free space: {}",
    "Calcul de l'espace utilisé…": "Calculating used space…",
    "{} jeu(x) installé(s) — {} utilisés": "{} game(s) installed — {} used",
    "Téléchargement": "Downloads",
    "Supprimer les archives après installation": "Delete archives after installation",
    "Vérifier les mises à jour au démarrage": "Check for updates at startup",
    "Affichage": "Display",
    "Lecture automatique des vidéos": "Autoplay videos",
    "Couper le son des vidéos": "Mute videos",
    "Intégrations": "Integrations",
    "Afficher le jeu en cours sur Discord": "Show current game on Discord",
    "Langue": "Language",
    "Redémarrez le launcher pour appliquer la langue.": "Restart the launcher to apply the language.",
    "Mises à jour": "Updates",
    "Launcher v{}  ·  Catalogue v{}": "Launcher v{}  ·  Catalog v{}",
    "Actualiser le catalogue": "Refresh catalog",
    "Vérifier les mises à jour": "Check for updates",
    "Actualisation du catalogue…": "Refreshing catalog…",
    "Vérification des mises à jour…": "Checking for updates…",
    "Catalogue mis à jour en v{}": "Catalog updated to v{}",
    "Catalogue déjà à jour": "Catalog already up to date",
    "Tout est à jour": "Everything is up to date",
    "À propos": "About",
    "Launcher pour les jeux Harry Potter sur PC.": "Launcher for the Harry Potter PC games.",
    "Site web": "Website",
    "Rejoindre le Discord": "Join the Discord",
    "❤ Soutenir sur Ko-fi": "❤ Support on Ko-fi",
    "Le projet est gratuit — un café aide à payer l'hébergement !":
        "The project is free — a coffee helps pay for hosting!",
    "Fermer": "Close",

    # ── Action panel / boutons ──
    "TÉLÉCHARGER": "DOWNLOAD",
    "Télécharger {}": "Download {}",
    "JOUER": "PLAY",
    "Jouer à {}": "Play {}",
    "DÉSINSTALLER": "UNINSTALL",
    "Désinstaller {}": "Uninstall {}",
    "Annuler": "Cancel",
    "Annuler le téléchargement": "Cancel download",
    "Installation… %p%": "Installing… %p%",
    "Mise à jour disponible : v{} → v{}": "Update available: v{} → v{}",
    "Mettre à jour": "Update",

    # ── Download bar / progression ──
    "Téléchargement en cours…": "Downloading…",
    "Installation en cours…": "Installing…",
    "Installation… {}%": "Installing… {}%",
    "Téléchargement :": "Download:",
    "~{}s restantes": "~{}s left",
    "~{} min restantes": "~{} min left",
    "~{}h restantes": "~{}h left",
    " — partie {}/{}": " — part {}/{}",

    # ── Main window / notifications ──
    "Prêt": "Ready",
    "{} mise(s) à jour disponible(s)": "{} update(s) available",
    "Accio Launcher v{} est disponible !": "Accio Launcher v{} is available!",
    "Télécharger": "Download",
    "Téléchargement de la mise à jour…": "Downloading update…",
    "Téléchargement de la mise à jour… {}%": "Downloading update… {}%",
    "Redémarrage…": "Restarting…",
    "Échec du téléchargement — ouverture de la page de release":
        "Download failed — opening the release page",
    "Catalogue mis à jour (v{})": "Catalog updated (v{})",
    "Mise à jour disponible pour {}": "Update available for {}",
    "{} jeux ont une mise à jour disponible": "{} games have an update available",
    "{} installé avec succès ✓": "{} installed successfully ✓",
    "Téléchargement terminé": "Download finished",
    "{} est prêt à jouer !": "{} is ready to play!",
    "Retour de {} — Bon jeu !": "Welcome back from {} — enjoy!",
    "Accio Launcher — En jeu : {}": "Accio Launcher — In game: {}",
    "Restaurer Accio Launcher": "Restore Accio Launcher",
    "Quitter": "Quit",
    "Réduire": "Minimize",
    "Agrandir": "Maximize",

    # ── Opérations ──
    "Un téléchargement ou installation est déjà en cours.":
        "A download or installation is already in progress.",
    "Téléchargement de {} v{}…": "Downloading {} v{}…",
    "Téléchargement annulé.": "Download cancelled.",
    "Installation de {}…": "Installing {}…",
    "{} installé avec succès !": "{} installed successfully!",
    "Vérification de {}…": "Verifying {}…",
    "Aucune version disponible.": "No version available.",
    "Installation incomplète.": "Incomplete installation.",
    "Installation incomplète": "Incomplete installation",
    "L'installation semble incomplète : l'exécutable du jeu est introuvable.\nL'archive est peut-être corrompue.":
        "The installation looks incomplete: the game executable is missing.\nThe archive may be corrupted.",
    "Échec du téléchargement": "Download failed",
    "Le téléchargement a échoué.\nVérifiez votre connexion internet et réessayez.":
        "The download failed.\nCheck your internet connection and try again.",
    "Échec de l'installation": "Installation failed",
    "L'installation a échoué.\nL'archive est peut-être corrompue. Réessayez le téléchargement.":
        "The installation failed.\nThe archive may be corrupted. Try downloading again.",
    "Erreur d'installation : {}": "Installation error: {}",
    "Erreur : {}": "Error: {}",

    # ── Handlers (dialogues) ──
    "Téléchargement déjà en cours": "Download already in progress",
    "Un téléchargement est déjà en cours pour {}.\n\nVeuillez attendre la fin avant d'en lancer un autre.":
        "A download is already in progress for {}.\n\nPlease wait for it to finish first.",
    "Téléchargement déjà en cours pour ce jeu.": "A download is already in progress for this game.",
    "Espace disque insuffisant": "Not enough disk space",
    "Il faut environ {} d'espace libre.\nActuellement {} disponibles.":
        "About {} of free space is required.\nCurrently {} available.",
    "Visual C++ manquant": "Visual C++ missing",
    "Le Visual C++ Redistributable x86 (2015-2022) n'est pas installé.\nIl est nécessaire pour lancer les jeux.\n\nVoulez-vous ouvrir la page de téléchargement ?":
        "The Visual C++ Redistributable x86 (2015-2022) is not installed.\nIt is required to launch the games.\n\nOpen the download page?",
    "Impossible de lancer le jeu.": "Unable to launch the game.",
    "Lancement de {}…": "Launching {}…",
    "Confirmer la désinstallation": "Confirm uninstall",
    "Voulez-vous vraiment désinstaller {} ?": "Really uninstall {}?",
    "Sauvegardes conservées": "Saves kept",
    "Les sauvegardes et la configuration dans Mes Documents ont été conservées.":
        "Your saves and configuration in My Documents were kept.",
    "{} désinstallé.": "{} uninstalled.",
    "Mise à jour disponible": "Update available",
    "Mettre à jour de v{} vers v{} ?\n\nChangements :\n{}\n\nLa version actuelle sera remplacée une fois le téléchargement terminé.":
        "Update from v{} to v{}?\n\nChanges:\n{}\n\nThe current version will be replaced once the download completes.",
    "Gérer les versions": "Manage versions",
    "Installer depuis un fichier local…": "Install from a local file…",
    "Sélectionner une archive de jeu": "Select a game archive",
    "Installation de {} depuis un fichier local…": "Installing {} from a local file…",
    "J'ai déjà ce jeu — localiser l'installation…": "I already own this game — locate it…",
    "Vérifier / réparer les fichiers": "Verify / repair files",
    "L'archive de {} va être re-téléchargée (avec vérification d'intégrité quand elle est disponible) puis réinstallée par-dessus les fichiers existants.\n\nLes sauvegardes et la configuration ne sont pas touchées.\n\nContinuer ?":
        "The archive for {} will be downloaded again (with integrity check when available) and reinstalled over the existing files.\n\nSaves and configuration are not affected.\n\nContinue?",
    "Localiser l'installation de {}": "Locate the installation of {}",
    "Import impossible": "Cannot import",
    "Importer ce jeu": "Import this game",
    "Le dossier va être déplacé :\n\n{}\n→ {}\n\nLe jeu sera marqué en version {} (version réelle inconnue — utilisez « Vérifier / réparer » en cas de doute).\n\nContinuer ?":
        "The folder will be moved:\n\n{}\n→ {}\n\nThe game will be marked as version {} (actual version unknown — use “Verify / repair” if unsure).\n\nContinue?",
    "Déplacement impossible :\n{}": "Could not move the folder:\n{}",
    "{} importé avec succès !": "{} imported successfully!",
    "Ce jeu ne supporte pas l'import d'une installation existante.":
        "This game does not support importing an existing installation.",
    "L'exécutable attendu est introuvable :\n{}\n\nChoisissez le dossier du jeu qui contient « {} ».":
        "The expected executable was not found:\n{}\n\nPick the game folder that contains “{}”.",
    "Un dossier existe déjà à l'emplacement cible :\n{}\n\nDésinstallez d'abord la copie existante.":
        "A folder already exists at the target location:\n{}\n\nUninstall the existing copy first.",
    "Le dossier est sur un autre disque que le dossier d'installation.\nDéplacez-le manuellement, ou changez le dossier d'installation dans les Paramètres.":
        "The folder is on a different drive than the install folder.\nMove it manually, or change the install folder in Settings.",

    # ── Versions dialog ──
    "Versions — {}": "Versions — {}",
    "recommandée": "recommended",
    "installée": "installed",
    "Mettre à jour vers v{}": "Update to v{}",
    "Revenir à v{}": "Roll back to v{}",
    "Installer v{}": "Install v{}",
    "Confirmer": "Confirm",
    "installer": "install",
    "supprimer la version actuelle et installer": "replace the current version and install",
    "Ceci va {} la version {}.\nContinuer ?": "This will {} version {}.\nContinue?",

    # ── Info panel ──
    "Lire la suite…": "Read more…",
    "Réduire le texte": "Show less",
    "Versions et changelog": "Versions & changelog",
    "Version {}": "Version {}",

    # ── Stats de jeu ──
    "{} min de jeu": "{} min played",
    "{} h de jeu": "{} h played",
    "{} h {} min de jeu": "{} h {} min played",
    "Dernière session : {}": "Last session: {}",
    "aujourd'hui": "today",
    "hier": "yesterday",
    "avant-hier": "two days ago",
    "il y a {} jours": "{} days ago",

    # ── Stepper téléchargement → vérification → installation ──
    "1/4 · Téléchargement": "1/4 · Download",
    "2/4 · Vérification": "2/4 · Verify",
    "3/4 · Installation": "3/4 · Install",
    "4/4 · Finalisation": "4/4 · Finalizing",
    "Vérification de l'archive…": "Verifying archive…",
    "Finalisation de l'installation…": "Finalizing installation…",
    # ── Jeu annoncé au catalogue, archives pas encore publiées ──
    "BIENTÔT DISPONIBLE": "COMING SOON",
    "Les fichiers de ce jeu ne sont pas encore en ligne.":
        "This game's files are not online yet.",
    "Pas encore en ligne": "Not online yet",
    "{} n'est pas encore téléchargeable — les fichiers arrivent bientôt.":
        "{} is not downloadable yet — the files are coming soon.",

    # ── Thèmes maisons ──
    "Thème :": "Theme:",
    "Thème": "Theme",
    "Redémarrez le launcher pour appliquer le thème.": "Restart the launcher to apply the theme.",
    "Redémarrer maintenant": "Restart now",
    "Relance automatique impossible — redémarrez manuellement.":
        "Automatic relaunch failed — please restart manually.",

    # ── Panneau Paramètres (sidebar) ──
    "Général": "General",
    "Téléchargements": "Downloads",
    "Vidéos": "Videos",
    "Particules saisonnières": "Seasonal particles",
    "Automatique (selon la date)": "Automatic (by date)",
    "Aucune": "None",
    "Noël ❄": "Christmas ❄",
    "Appliqué immédiatement.": "Applied immediately.",

    # ── Pastille téléchargements ──
    "{} téléchargement": "{} download",
    "{} téléchargements": "{} downloads",
    "Téléchargements cumulés de toutes les versions (GitHub)":
        "Cumulative downloads across all versions (GitHub)",
    "Poudlard (or)": "Hogwarts (gold)",
    "Gryffondor": "Gryffindor",
    "Serpentard": "Slytherin",
    "Serdaigle": "Ravenclaw",
    "Poufsouffle": "Hufflepuff",

    # ── Remerciement Ko-fi (cap 10 h, une seule fois) ──
    "Déjà 10 h de magie retrouvée ✨ Si le launcher te plaît, un café fait plaisir — clique ici ❤":
        "10 hours of magic already ✨ If you enjoy the launcher, a coffee always helps — click here ❤",

    # ── Rapport de crash ──
    "Accio Launcher — Erreur inattendue": "Accio Launcher — Unexpected error",
    "Une erreur inattendue s'est produite. Tu peux copier le rapport "
    "(à coller sur le Discord) ou ouvrir une issue GitHub pré-remplie.":
        "An unexpected error occurred. You can copy the report "
        "(to paste on Discord) or open a pre-filled GitHub issue.",
    "Copier le rapport": "Copy report",
    "Copié ✓": "Copied ✓",
    "Ouvrir une issue GitHub": "Open a GitHub issue",
    "Redémarrer le launcher": "Restart the launcher",

    # ── Divers ──
    "Launcher v{} disponible !": "Launcher v{} available!",
}
