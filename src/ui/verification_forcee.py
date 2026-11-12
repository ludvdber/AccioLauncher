"""« Vérifier les mises à jour » depuis les Paramètres (rubrique À propos).

Extrait de `main_window` (plafond de lignes). Ce qui est propre à ce geste :
parler au dialogue qui l'a demandé — et seulement tant qu'il vit — puis dire
le RÉSULTAT sans affirmer ce qu'on n'a pas vu. Ce qui arrive au catalogue ou
au launcher est rendu à la fenêtre par les rappels, comme au démarrage.

Un seul geste depuis le 2026-11-12 : « Actualiser le catalogue » lançait le
MÊME vérificateur, le launcher en moins ; deux boutons dont l'un incluait
l'autre. Le résultat dit donc ce qui a changé, tout ce qui a changé.
"""

from src.core.i18n import tr, trn


def verifier(checker, dlg, *, sur_catalogue, sur_launcher, en_ligne, url_launcher) -> None:
    """Lance `checker` et rend compte à `dlg`.

    `sur_catalogue(catalogue)` et `sur_launcher(version, url, asset, sha, notes)`
    sont ceux de la fenêtre ; `en_ligne()` et `url_launcher()` sont LUS à la
    fin, pas avant : `network_status` est la dernière instruction de `run()`.
    """
    etat: dict = {"catalogue": "", "launcher": "", "jeux": 0, "vivant": True}
    dlg.destroyed.connect(lambda *_: etat.update(vivant=False))

    def vivant() -> bool:
        if not etat["vivant"]:
            return False
        try:
            dlg.isVisible()
            return True
        except RuntimeError:     # objet C++ détruit sans que `destroyed` soit passé
            etat["vivant"] = False
            return False

    def catalogue(nouveau) -> None:
        etat["catalogue"] = nouveau.catalog_version
        sur_catalogue(nouveau)
        if vivant():
            dlg.update_catalog_version(nouveau.catalog_version)

    def launcher(version, url, asset_url="", asset_sha256="", notes="") -> None:
        # Tous les arguments sont DÉCLARÉS : PyQt tronque en silence ceux qu'un
        # slot n'a pas, et l'empreinte SHA-256 partait vide — l'exe d'auto-update
        # était installé sans être vérifié (tests/test_notif_update.py).
        sur_launcher(version, url, asset_url, asset_sha256, notes)
        etat["launcher"] = version

    def jeux(nombre: int) -> None:
        etat["jeux"] = nombre

    def fin() -> None:
        if not vivant():
            return
        # Hors ligne, l'absence de catalogue est indistinguable d'un catalogue à
        # jour : sans ce test on répondait « Catalogue déjà à jour » sans avoir
        # rien vérifié (mesuré le 2026-08-28, les deux cas rendaient la MÊME chaîne).
        if not en_ligne():
            dlg.show_update_status(tr("Hors ligne : vérifiez la connexion, puis réessayez."), success=False)
            return
        # Chaque nouveauté sur sa ligne : un message n'efface plus l'autre
        # (« Catalogue déjà à jour » effaçait « Launcher vX disponible ! »,
        # grand audit du 2026-11-02).
        changes = []
        if etat["launcher"]:
            changes.append(tr("Launcher v{} disponible !").format(etat["launcher"]))
        if etat["catalogue"]:
            changes.append(tr("Catalogue mis à jour en v{}").format(etat["catalogue"]))
        if etat["jeux"]:
            changes.append(trn(etat["jeux"], "1 jeu a une mise à jour disponible",
                               "{} jeux ont une mise à jour disponible").format(etat["jeux"]))
        if changes:
            dlg.show_update_status("\n".join(changes))
        elif url_launcher() or dlg.jeux_a_mettre_a_jour():
            # Une mise à jour déjà connue attend (launcher annoncé, jeu pas
            # encore mis à jour) : « Tout est à jour » serait faux.
            dlg.show_update_status(tr("Catalogue déjà à jour"))
        else:
            dlg.show_update_status(tr("Tout est à jour"))

    checker.catalog_updated.connect(catalogue)
    checker.launcher_update.connect(launcher)
    checker.update_counts.connect(jeux)
    checker.finished.connect(fin)
    checker.start()
