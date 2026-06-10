"""Utilitaires de formatage — tailles, vitesses, durées. Aucune dépendance Qt."""


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
        return f"~{int(seconds)}s restantes"
    minutes = seconds / 60
    if minutes < 60:
        return f"~{int(minutes)} min restantes"
    hours = minutes / 60
    return f"~{hours:.1f}h restantes"


def format_progress_line(downloaded: int, total: int, speed: float,
                         eta_seconds: float, *, with_label: bool = False) -> str:
    """Compose la ligne de statut d'un téléchargement (factorisé entre les widgets).

    `with_label=True` préfixe par 'Téléchargement : ' (zone détail),
    `False` donne uniquement le pourcentage (barre persistante).
    """
    if total <= 0:
        return ""
    pct = downloaded * 100 // total
    head = f"Téléchargement : {pct}%" if with_label else f"{pct}%"
    parts = [head, f"{format_bytes(downloaded)} / {format_bytes(total)}", format_speed(speed)]
    eta = format_eta(eta_seconds)
    if eta:
        parts.append(eta)
    return " — ".join(parts)


def append_part_info(line: str, current: int, total: int) -> str:
    """Ajoute (ou remplace) le suffixe ' — partie X/Y' à une ligne de statut."""
    base = line.split(" — partie ")[0]
    return f"{base} — partie {current}/{total}"
