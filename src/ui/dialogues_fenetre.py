"""Les deux questions que pose la fenêtre principale.

Extrait de `main_window` (plafond de lignes). Ce sont des QUESTIONS, donc de
vrais dialogues (les toasts sont pour ce qui n'attend rien), et toutes deux
affichent du texte venu de l'extérieur : `FenetreMessage` les pose toujours en
texte brut. Boutons NOMMÉS, jamais `StandardButton` (règle 116 de CLAUDE.md).
"""

from PyQt6.QtCore import Qt

from src.core.i18n import tr
from src.ui.fenetre_message import FenetreMessage


def _boite(parent, titre: str, texte: str, detail: str, conserve: str = "") -> FenetreMessage:
    boite = FenetreMessage(parent)
    boite.setWindowTitle(titre)
    boite.setTextFormat(Qt.TextFormat.PlainText)   # sans effet ici : le dit quand même
    boite.setText(texte)
    boite.setInformativeText(detail)
    if conserve:
        boite.setConserve(conserve)
    return boite


def proposer_mise_a_jour(parent, version: str, notes: str, auto: bool) -> bool:
    """« Mettre à jour maintenant ? » — True si accepté.

    Ce que la version APPORTE passe AVANT la façon dont elle s'installe : on
    demande d'accepter de remplacer un exécutable, la première chose à dire est
    donc ce qui change. Absent (release sans notes, hors ligne, API limitée) →
    on n'invente rien et on se tait. Aucun en-tête « Nouveautés : » ajouté :
    les notes portent DÉJÀ leur titre, et la boîte de la 1.0.6 l'affichait
    deux fois de suite.
    """
    mecanique = (
        tr("La mise à jour est téléchargée et installée automatiquement ; "
           "le launcher redémarre ensuite. Vos jeux et vos sauvegardes ne "
           "sont pas touchés.")
        if auto else
        tr("La page de téléchargement va s'ouvrir dans votre navigateur."))
    notes = notes.strip()
    boite = _boite(parent, tr("Mise à jour disponible"),
                   tr("Accio Launcher v{} est disponible !").format(version),
                   f"{notes}\n\n{mecanique}" if notes else mecanique)
    maintenant = boite.addButton(tr("Mettre à jour maintenant"),
                                 FenetreMessage.ButtonRole.AcceptRole)
    boite.addButton(tr("Plus tard"), FenetreMessage.ButtonRole.RejectRole)
    boite.setDefaultButton(maintenant)
    boite.exec()
    return boite.clickedButton() is maintenant


def confirmer_fermeture(parent, nom_du_jeu: str | None, phase: str) -> bool:
    """« Quitter pendant une opération ? » — True si on ferme quand même.

    Le message DIFFÈRE selon la phase, parce que la perte diffère : un
    téléchargement reprend où il s'est arrêté (`.part` + `Range`), une
    installation est à refaire — l'archive, elle, reste en cache. « Êtes-vous
    sûr ? » sans dire ce qu'on risque fait deviner, et qui devine clique.
    """
    boite = _boite(
        parent, tr("Opération en cours"),
        tr("« {} » est en cours.").format(nom_du_jeu if nom_du_jeu else tr("un jeu")),
        tr("Le téléchargement reprendra où il s'est arrêté au prochain "
           "démarrage — rien n'est perdu.")
        if phase == "download" else
        tr("L'installation devra être refaite depuis le début. L'archive "
           "déjà téléchargée est conservée : il n'y aura rien à "
           "re-télécharger."))
    quitter = boite.addButton(tr("Quitter quand même"), FenetreMessage.ButtonRole.DestructiveRole)
    boite.setDefaultButton(boite.addButton(tr("Continuer"), FenetreMessage.ButtonRole.RejectRole))
    boite.exec()
    return boite.clickedButton() is quitter
