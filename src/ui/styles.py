# Palette Poudlard / Carte du Maraudeur
COLOR_BG_PRIMARY = "#1a1a2e"
COLOR_BG_CARD = "#16213e"
COLOR_ACCENT_GOLD = "#d4a017"
COLOR_ACCENT_GOLD_LIGHT = "#e6b422"
COLOR_ACCENT_RED = "#c0392b"
COLOR_ACCENT_GREEN = "#27ae60"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_SECONDARY = "#a0a0a0"
COLOR_BORDER = "#2c3e6b"

MAIN_STYLE = f"""
QMainWindow {{
    background-color: {COLOR_BG_PRIMARY};
}}

QScrollArea {{
    border: none;
    background-color: {COLOR_BG_PRIMARY};
}}

QWidget#centralContainer {{
    background-color: {COLOR_BG_PRIMARY};
}}

QLabel {{
    color: {COLOR_TEXT};
}}

QLabel#headerTitle {{
    font-size: 28px;
    font-weight: bold;
    color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #c8a415, stop:0.5 #f0d060, stop:1 #c8a415);
}}

QLabel#headerSubtitle {{
    font-size: 14px;
    color: {COLOR_TEXT_SECONDARY};
}}

/* ---------- Séparateur header ---------- */

QFrame#headerSeparator {{
    background-color: {COLOR_BORDER};
    max-height: 1px;
    margin-left: 40px;
    margin-right: 40px;
}}

/* ---------- Barre de statut ---------- */

QStatusBar {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_SECONDARY};
    font-size: 12px;
    border-top: 1px solid {COLOR_BORDER};
}}

/* ---------- Barre de menu ---------- */

QMenuBar {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT};
    border-bottom: 1px solid {COLOR_BORDER};
    padding: 2px;
}}

QMenuBar::item {{
    padding: 4px 12px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {COLOR_BORDER};
}}

QMenu {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 24px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {COLOR_BORDER};
}}

QMenu::separator {{
    height: 1px;
    background-color: {COLOR_BORDER};
    margin: 4px 8px;
}}

/* ---------- Cartes de jeu ---------- */

QFrame#gameCard {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
}}

QFrame#gameCard:hover {{
    border: 1px solid {COLOR_ACCENT_GOLD};
}}

QLabel#cardTitle {{
    font-size: 16px;
    font-weight: bold;
    color: {COLOR_TEXT};
}}

QLabel#cardMeta {{
    font-size: 12px;
    color: {COLOR_TEXT_SECONDARY};
}}

QLabel#cardDescription {{
    font-size: 12px;
    color: {COLOR_TEXT_SECONDARY};
}}

QLabel#cardSize {{
    font-size: 12px;
    color: {COLOR_TEXT_SECONDARY};
}}

QLabel#placeholderText {{
    font-size: 18px;
    font-weight: bold;
    color: {COLOR_ACCENT_GOLD};
}}

QLabel#downloadLabel {{
    font-size: 11px;
    color: {COLOR_TEXT_SECONDARY};
}}

/* ---------- Boutons ---------- */

QPushButton#btnDownload {{
    background-color: {COLOR_ACCENT_GOLD};
    color: #000000;
    font-weight: bold;
    font-size: 14px;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
}}

QPushButton#btnDownload:hover {{
    background-color: {COLOR_ACCENT_GOLD_LIGHT};
}}

QPushButton#btnPlay {{
    background-color: {COLOR_ACCENT_GREEN};
    color: #ffffff;
    font-weight: bold;
    font-size: 16px;
    border: none;
    border-radius: 8px;
    padding: 12px 16px;
}}

QPushButton#btnPlay:hover {{
    background-color: #2ecc71;
}}

QPushButton#btnUninstall {{
    background: transparent;
    color: {COLOR_ACCENT_RED};
    font-size: 11px;
    border: none;
    padding: 4px;
}}

QPushButton#btnUninstall:hover {{
    color: #e74c3c;
    text-decoration: underline;
}}

QPushButton#btnCancel {{
    background-color: {COLOR_ACCENT_RED};
    color: #ffffff;
    font-size: 11px;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
}}

QPushButton#btnCancel:hover {{
    background-color: #e74c3c;
}}

/* ---------- Barre de progression ---------- */

QProgressBar {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    background-color: {COLOR_BG_PRIMARY};
    text-align: center;
    color: {COLOR_TEXT};
    font-size: 11px;
    height: 20px;
}}

QProgressBar::chunk {{
    background-color: {COLOR_ACCENT_GOLD};
    border-radius: 5px;
}}
"""
