# Palette Poudlard — Launcher AAA
COLOR_BG_PRIMARY = "#060611"
COLOR_BG_CARD = "#0f1528"
COLOR_BG_CAROUSEL = "rgba(6, 6, 17, 0.92)"
COLOR_ACCENT_GOLD = "#d6a72c"
COLOR_ACCENT_GOLD_LIGHT = "#f0d060"
COLOR_ACCENT_GOLD_DARK = "#9a7209"
COLOR_ACCENT_RED = "#c0392b"
COLOR_ACCENT_GREEN = "#2ecc71"
COLOR_ACCENT_GREEN_DARK = "#1a9c54"
COLOR_TEXT = "#eaeaea"
COLOR_TEXT_SECONDARY = "#8a8aaa"
COLOR_BORDER = "#1a2744"

MAIN_STYLE = f"""
QMainWindow {{
    background-color: {COLOR_BG_PRIMARY};
}}

QWidget#centralContainer {{
    background-color: {COLOR_BG_PRIMARY};
}}

/* ---------- Barre de menu ---------- */

QMenuBar {{
    background-color: transparent;
    color: {COLOR_TEXT_SECONDARY};
    border: none;
    padding: 2px;
}}

QMenuBar::item {{
    padding: 4px 12px;
    border-radius: 4px;
    background: transparent;
}}

QMenuBar::item:selected {{
    background-color: rgba(255, 255, 255, 0.08);
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

/* ---------- Barre de statut ---------- */

QStatusBar {{
    background-color: {COLOR_BG_PRIMARY};
    color: {COLOR_TEXT_SECONDARY};
    font-size: 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.04);
}}

/* ---------- Zone carrousel ---------- */

QWidget#carouselBar {{
    background: transparent;
    border: none;
}}

/* ---------- Boutons d'action (zone centrale) ---------- */

/* btnDownload, btnPlay, btnUninstall sont peints par GlowButton.paintEvent */

QPushButton#btnCancel {{
    background-color: {COLOR_ACCENT_RED};
    color: #ffffff;
    font-size: 12px;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
}}

QPushButton#btnCancel:hover {{
    background-color: #e74c3c;
}}

/* ---------- Focus clavier visible (A11Y) ----------
   L'anneau ne s'affiche QUE si le focus vient du clavier : la propriété
   `focusClavier` est posée par src/ui/focus_visible.py selon la raison du
   focus. Sans elle, Qt cerclait le premier bouton de la chaîne dès l'ouverture
   de la fenêtre (personne n'avait rien fait) et laissait l'anneau après un
   simple clic. Ne pas retirer le sélecteur : c'est le seul repère au clavier. */

QPushButton[focusClavier="true"]:focus, QLabel[focusClavier="true"]:focus,
QSlider[focusClavier="true"]:focus, QProgressBar[focusClavier="true"]:focus,
QLineEdit[focusClavier="true"]:focus, QComboBox[focusClavier="true"]:focus {{
    outline: 2px solid {COLOR_ACCENT_GOLD};
    outline-offset: 1px;
}}

QPushButton#btnMute {{
    background: rgba(0, 0, 0, 0.5);
    color: {COLOR_TEXT};
    border: none;
    border-radius: 14px;
    font-size: 16px;
    padding: 4px;
    min-width: 28px;
    min-height: 28px;
}}

QPushButton#btnMute:hover {{
    background: rgba(0, 0, 0, 0.7);
}}

/* ---------- Barre de progression ---------- */

QProgressBar {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    background-color: rgba(6, 6, 17, 0.6);
    text-align: center;
    color: {COLOR_TEXT};
    font-size: 12px;
    font-weight: bold;
    min-height: 30px;
    max-width: 400px;
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_ACCENT_GOLD_DARK}, stop:1 {COLOR_ACCENT_GOLD_LIGHT});
    border-radius: 7px;
}}

/* ---------- Labels zone détail ---------- */

QLabel#gameTitle {{
    font-size: 36px;
    font-weight: 900;
    color: {COLOR_TEXT};
    letter-spacing: 1px;
}}

QLabel#gameMeta {{
    font-size: 14px;
    color: {COLOR_TEXT_SECONDARY};
    letter-spacing: 1px;
}}

QLabel#gameDescription {{
    font-size: 15px;
    color: rgba(176, 176, 200, 0.75);
    line-height: 1.5;
}}

QLabel#downloadLabel {{
    font-size: 12px;
    color: {COLOR_TEXT_SECONDARY};
}}

QLabel#sizeLabel {{
    font-size: 14px;
    color: {COLOR_TEXT_SECONDARY};
}}

/* ---------- Dialogues thématisés (QMessageBox & co.) ----------
   Les QMessageBox gris Windows cassaient l'immersion ; les dialogues parentés
   à la fenêtre héritent de cette feuille. */

QMessageBox, QInputDialog {{
    background-color: #0d0d1a;
}}

QMessageBox QLabel, QInputDialog QLabel {{
    color: {COLOR_TEXT};
    font-size: 13px;
    background: transparent;
}}

QMessageBox QPushButton, QInputDialog QPushButton {{
    background-color: #16213e;
    color: {COLOR_TEXT};
    border: 1px solid #2c3e6b;
    border-radius: 6px;
    padding: 6px 18px;
    font-size: 13px;
    min-width: 70px;
}}

QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{
    border-color: {COLOR_ACCENT_GOLD};
    color: {COLOR_ACCENT_GOLD_LIGHT};
}}

QMessageBox QPushButton:default {{
    background-color: rgba(214, 167, 44, 0.18);
    border-color: rgba(214, 167, 44, 0.55);
    color: {COLOR_ACCENT_GOLD_LIGHT};
    font-weight: bold;
}}

QToolTip {{
    background-color: #0d0d1a;
    color: {COLOR_TEXT};
    border: 1px solid rgba(214, 167, 44, 0.45);
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}
"""
