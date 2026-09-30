"""« Vérifier les mises à jour » depuis les Paramètres.

Extrait de `main_window` (plafond de lignes). Ce qui est propre à ce geste :
parler au dialogue qui l'a demandé — et seulement tant qu'il vit — puis dire
le RÉSULTAT sans affirmer ce qu'on n'a pas vu. Ce qui arrive au catalogue ou
au launcher est rendu à la fenêtre par les rappels, comme au démarrage.
"""

from src.core.i18n import tr


def verifier(checker, dlg, *, catalog_only: bool, sur_catalogue, sur_launcher,
             en_ligne, url_launcher) -> None:
    """Lance `checker` et rend compte à `dlg`.

    `sur_catalogue(catalogue)` et `sur_launcher(version, url, asset, sha, notes)`
    sont ceux de la fenêtre ; `en_ligne()` et `url_launcher()` sont LUS à la
    fin, pas avant : `network_status` est la dernière instruction de `run()`.
    """
    etat = {"catalogue": False, "vivant": True}
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
        etat["catalogue"] = True
        sur_catalogue(nouveau)
        if vivant():
            dlg.update_catalog_version(nouveau.catalog_version)

    def launcher(version, url, asset_url="", asset_sha256="", notes="") -> None:
        # Tous les arguments sont DÉCLARÉS : PyQt tronque en silence ceux qu'un
        # slot n'a pas, et l'empreinte SHA-256 partait vide — l'exe d'auto-update
        # était installé sans être vérifié (tests/test_notif_update.py).
        sur_launcher(version, url, asset_url, asset_sha256, notes)
        if vivant():
            dlg.show_update_status(tr("Launcher v{} disponible !").format(version))

    def fin() -> None:
        if not vivant():
            return
        # Hors ligne, l'absence de catalogue est indistinguable d'un catalogue à
        # jour : sans ce test on répondait « Catalogue déjà à jour » sans avoir
        # rien vérifié (mesuré le 2026-08-28, les deux cas rendaient la MÊME chaîne).
        if not en_ligne():
            dlg.show_update_status(tr("Hors ligne — vérification impossible."), success=False)
        elif not etat["catalogue"]:
            dlg.show_update_status(tr("Catalogue déjà à jour"))
        elif not catalog_only and not url_launcher():
            dlg.show_update_status(tr("Tout est à jour"))

    checker.catalog_updated.connect(catalogue)
    if not catalog_only:
        checker.launcher_update.connect(launcher)
    checker.finished.connect(fin)
    checker.start()
