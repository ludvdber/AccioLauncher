"""Le texte de soumission à Microsoft (`.github/microsoft-submission.md`)."""

from pathlib import Path

SOUMISSION = Path(__file__).resolve().parent.parent / ".github" / "microsoft-submission.md"


def _bloc() -> str:
    texte = SOUMISSION.read_text(encoding="utf-8")
    bloc = texte.split("```text\n")[1].split("```")[0]
    # Ce que pose le workflow « release » : une étiquette et une empreinte.
    return bloc.replace("{TAG}", "v10.10.10").replace("{SHA256}", "0" * 64)


def test_le_formulaire_accepte_le_texte():
    """Le champ « Additional information » s'arrête à 1 900 caractères ; le
    texte en faisait 1 859, sans rien qui le tienne (audit du 2026-10-29)."""
    assert len(_bloc()) < 1900


def test_vgmstream_n_est_plus_dit_embarque():
    """Depuis la 1.3.1, vgmstream se télécharge à la première écoute : la
    soumission disait encore « Bundles 7-Zip and vgmstream-cli »."""
    assert "Bundles 7-Zip and vgmstream" not in _bloc()
