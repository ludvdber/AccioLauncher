"""Utilitaires de formatage — tailles, vitesses, durées. Aucune dépendance Qt.

Toutes les chaînes visibles passent par tr() (i18n FR/EN).
"""

from datetime import date, datetime

from src.core.i18n import tr


def format_size(size_mb: int) -> str:
    """Formate une taille en Mo/Go (entrée en mégaoctets)."""
    if size_mb >= 1000:
        return f"{size_mb / 1000:.1f} Go"
    return f"{size_mb} Mo"


def format_bytes(b: int) -> str:
    """Formate une taille en Mo/Go (entrée en octets)."""
    mb = b / (1024 * 1024)
    if mb >= 1000:
        return f"{mb / 1000:.1f} Go"
    return f"{mb:.0f} Mo"


def format_speed(bytes_per_sec: float) -> str:
    """Formate une vitesse en Ko/s ou Mo/s."""
    mb = bytes_per_sec / (1024 * 1024)
    if mb >= 1.0:
        return f"{mb:.1f} Mo/s"
    kb = bytes_per_sec / 1024
    return f"{kb:.0f} Ko/s"


def format_eta(seconds: float) -> str:
    """Formate un temps restant estimé."""
    if seconds < 0 or seconds > 86400:
        return ""
    if seconds < 60:
        return tr("~{}s restantes").format(int(seconds))
    minutes = seconds / 60
    if minutes < 60:
        return tr("~{} min restantes").format(int(minutes))
    hours = minutes / 60
    return tr("~{}h restantes").format(f"{hours:.1f}")


def format_progress_line(downloaded: int, total: int, speed: float,
                         eta_seconds: float, *, with_label: bool = False) -> str:
    """Compose la ligne de statut d'un téléchargement (factorisé entre les widgets).

    `with_label=True` préfixe par 'Téléchargement : ' (zone détail),
    `False` donne uniquement le pourcentage (barre persistante).
    """
    if total <= 0:
        return ""
    pct = downloaded * 100 // total
    head = f"{tr('Téléchargement :')} {pct}%" if with_label else f"{pct}%"
    parts = [head, f"{format_bytes(downloaded)} / {format_bytes(total)}", format_speed(speed)]
    eta = format_eta(eta_seconds)
    if eta:
        parts.append(eta)
    return " — ".join(parts)


def append_part_info(line: str, current: int, total: int) -> str:
    """Ajoute (ou remplace) le suffixe ' — partie X/Y' à une ligne de statut."""
    template = tr(" — partie {}/{}")
    marker = template.split("{}")[0]  # ' — partie ' / ' — part '
    base = line.split(marker)[0]
    return base + template.format(current, total)


# ─── Stats de jeu ───

def format_playtime(seconds: int) -> str:
    """Formate un temps de jeu cumulé : « 45 min de jeu », « 14 h de jeu »…

    Arrondi à la minute (minimum 1 min — les sessions plus courtes sont
    filtrées en amont).
    """
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return tr("{} min de jeu").format(minutes)
    hours, rem = divmod(minutes, 60)
    if hours < 10 and rem > 0:
        return tr("{} h {} min de jeu").format(hours, rem)
    return tr("{} h de jeu").format(hours)


def format_relative_date(iso_date: str, today: date | None = None) -> str:
    """Date relative en clair : « aujourd'hui », « hier », « il y a N jours »…

    Au-delà de 30 jours (ou format invalide) : date JJ/MM/AAAA telle quelle.
    """
    try:
        d = datetime.fromisoformat(iso_date).date()
    except ValueError:
        return iso_date
    today = today or date.today()
    delta = (today - d).days
    if delta <= 0:
        return tr("aujourd'hui")
    if delta == 1:
        return tr("hier")
    if delta == 2:
        return tr("avant-hier")
    if delta <= 30:
        return tr("il y a {} jours").format(delta)
    return d.strftime("%d/%m/%Y")
