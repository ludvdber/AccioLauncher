"""Les rubriques des réglages d'un jeu se bâtissent à leur première ouverture (`GameSettingsDialog`,
`_montrer_rubrique`, 2026-11-19) : un test qui lit la fenêtre entière les ouvre d'abord, comme le joueur."""


def toutes(dlg):
    """Ouvre chaque rubrique, puis revient à celle qui était ouverte ; rend la fenêtre."""
    ouverte = next((b for b in dlg._onglets.values() if b.isChecked()), None)
    for pastille in dlg._onglets.values():
        pastille.click()
    if ouverte is not None:
        ouverte.click()
    return dlg


def pages(dlg):
    """Le contenu de chaque rubrique, dans l'ordre des pastilles, toutes bâties."""
    toutes(dlg)
    return [dlg._defile.widget(rang) for rang in range(dlg._defile.count())]
