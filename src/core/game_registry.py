"""Lecture et écriture des valeurs de registre d'un jeu (Windows uniquement).

Pourquoi un module à part
=========================
`post_install.apply_registry` est un stub aux défauts prouvés (valeur par défaut
au lieu de valeurs nommées, HKLM silencieusement redirigé vers HKCU, vue 64 bits).
Le besoin réel qui l'a rattrapé n'est d'ailleurs PAS un besoin d'installation :
HP7 lit sa LANGUE dans le registre, et la langue est une **préférence du joueur**,
qui doit pouvoir changer sans réinstaller. Elle s'écrit donc au LANCEMENT, d'après
un choix stocké par jeu, et pas une fois pour toutes après l'extraction.

Trois contraintes, relevées sur une vraie installation le 2026-08-21
====================================================================
* **Vue 32 bits.** Python est 64 bits, les jeux du catalogue sont 32 bits : sans
  `KEY_WOW64_32KEY` on écrit à côté de ce que le jeu lit (`WOW6432Node`).
* **Valeurs NOMMÉES et typées.** `Language` est un `REG_SZ`, mais la sous-clé
  « 1.0 » porte un `Language` en `REG_DWORD` : écrire tout en chaîne ne marche pas.
* **HKLM exige l'élévation.** On n'impose donc JAMAIS d'UAC pour rien : on lit
  d'abord (gratuit), on compare, et on n'écrit que si ça diffère réellement.
  L'écriture élevée passe par un .reg + « regedit /s », et **on relit derrière
  pour vérifier** — regedit est muet en mode silencieux, y compris quand il échoue.

Sous Linux : le registre du PRÉFIXE Wine
========================================
Le jeu tourne sous Wine, qui a son registre. Deux points seulement changent,
comme annoncé depuis le début : `disponible()`, et `_ecrire_eleve`, qui importe
le même `.reg` (même `construire_reg`, même barrière) par `regedit /S` dans le
préfixe, via le lanceur de compatibilité. La lecture ne lance rien : le
registre d'un préfixe est du texte, lu par `compat.lire_valeurs`. Pas d'UAC
sous Wine — mais la prévenance (`confirmer`) reste : on ne modifie pas le
réglage de quelqu'un sans le lui dire, quel que soit le système.
"""

import logging
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

log = logging.getLogger(__name__)

RUCHES = ("HKCU", "HKLM")

# Segments de clé interdits, quelle que soit la ruche. Le catalogue se met à jour
# À DISTANCE : ces chemins-là donnent une persistance au démarrage ou détournent
# le chargement d'un processus, et aucun jeu n'a la moindre raison d'y écrire.
# L'ancienne whitelist de `post_install` (« tout ce qui commence par Software\ »)
# acceptait Software\Microsoft\Windows\CurrentVersion\Run.
_SEGMENTS_INTERDITS = frozenset({
    "microsoft", "policies", "classes", "services", "run", "runonce",
    "runonceex", "winlogon", "image file execution options", "appcompatflags",
    "shellserviceobjectdelayload", "explorer", "windows nt", "currentversion",
})
_NOMS_INTERDITS = frozenset({
    "appinit_dlls", "userinit", "shell", "load", "run", "loadappinit_dlls",
})
_PROFONDEUR_MIN = 2      # « Software\Editeur\Jeu » au minimum

_RUCHES_LONGUES = {"HKCU": "HKEY_CURRENT_USER", "HKLM": "HKEY_LOCAL_MACHINE"}


def disponible() -> bool:
    """True si ce système a un registre que le launcher sait atteindre.

    Sous Windows, toujours. Sous Linux, celui du préfixe Wine — à condition
    qu'il existe : un lanceur de compatibilité ET un préfixe initialisé. Avant
    sa première préparation, il n'y a rien à lire, et écrire lancerait umu
    pendant que la fenêtre attend (umu peut alors télécharger Proton).

    On ne fait pas SEMBLANT : sans registre, la fiche n'affiche aucun
    sélecteur de langue (annoncer un réglage qu'on ne sait pas appliquer est un
    mensonge) et le lancement ne journalise pas un échec à chaque partie pour
    une chose qu'on n'a jamais tenté de faire.
    """
    if sys.platform == "win32":
        return True
    from src.core import compat
    return compat.lanceur() is not None and compat.pret(compat.prefixe())


def _controle(texte: str) -> bool:
    """True si le texte contient un caractère de contrôle (saut de ligne inclus).

    Ce n'est pas une coquetterie. Un .reg est un format LIGNE À LIGNE : une
    valeur portant un saut de ligne referme la chaîne, et la suite est relue
    comme du .reg — donc comme des instructions, importées par un regedit
    ÉLEVÉ. Démontré le 2026-08-21, le catalogue étant distant :

        Language = 'French<CRLF>[HKLM\\...\\CurrentVersion\\Run]<CRLF>"x"="evil.exe"'

    ressortait tel quel dans le fichier. Le doublement des antislashs limitait
    les dégâts, mais par ACCIDENT, pas par conception. Aucune langue de jeu n'a
    besoin d'un caractère de contrôle : on refuse, et le problème disparaît.
    """
    # Cc : C0, DEL et C1 (dont U+0085, « next line ») ; Zl / Zp : séparateurs
    # de ligne et de paragraphe Unicode. Aucun n'a sa place dans une valeur de
    # registre, et on n'a pas à savoir lesquels regedit prend pour un saut.
    return any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in texte)


def refus_de_cle(ruche: str, cle: str) -> str | None:
    """Raison de refuser cette clé, ou None si elle est acceptable.

    Fonction PURE : testable sans registre ni Windows, et c'est tout l'intérêt —
    c'est la seule barrière entre un catalogue distant et le registre système.
    """
    if ruche not in RUCHES:
        return "ruche non supportée (%r)" % (ruche,)
    if not isinstance(cle, str) or not cle.strip():
        return "chemin vide"
    if _controle(cle):
        return "caractère de contrôle dans le chemin"
    if "[" in cle or "]" in cle:
        # Délimiteurs de section d'un .reg : un crochet dans le chemin y ferait
        # n'importe quoi, et le nom de clé résultant serait de toute façon faux.
        return "crochet dans le chemin"
    segments = [s for s in cle.replace("/", "\\").split("\\") if s]
    if not segments or segments[0].lower() != "software":
        return "hors de Software"
    if ".." in segments:
        return "remontée de chemin"
    if len(segments) < _PROFONDEUR_MIN:
        return "chemin trop court (Software\\Editeur\\Jeu attendu)"
    for s in segments[1:]:
        if s.lower() in _SEGMENTS_INTERDITS:
            return "segment interdit (%r)" % (s,)
    return None


def refus_de_valeur(nom: str, valeur) -> str | None:
    """Raison de refuser cette valeur nommée, ou None. Pure.

    La valeur PAR DÉFAUT d'une clé est refusée exprès : c'est précisément ce que
    l'ancien stub écrivait, et c'est ce qui créait une sous-clé « Install Dir »
    au lieu de la valeur nommée que le jeu lit.
    """
    if not isinstance(nom, str) or not nom.strip():
        return "nom de valeur vide (la valeur par défaut n'est pas supportée)"
    if nom.lower() in _NOMS_INTERDITS:
        return "nom de valeur interdit (%r)" % (nom,)
    if _controle(nom):
        return "caractère de contrôle dans le nom"
    if isinstance(valeur, bool) or not isinstance(valeur, (str, int)):
        return "type non supporté (%s)" % type(valeur).__name__
    if isinstance(valeur, str) and _controle(valeur):
        return "caractère de contrôle dans la valeur (injection .reg)"
    if isinstance(valeur, int) and not 0 <= valeur <= 0xFFFFFFFF:
        return "entier hors des bornes d'un REG_DWORD"
    return None


def _echappe_reg(texte: str) -> str:
    """Échappe une chaîne pour le corps d'un fichier .reg (antislash et guillemet)."""
    return texte.replace("\\", "\\\\").replace('"', '\\"')


def construire_reg(ruche: str, cle: str, valeurs: dict, vue: int = 32) -> str:
    """Contenu d'un fichier .reg posant `valeurs` sous cette clé. Pure.

    La vue 32 bits ne s'exprime pas par un drapeau dans un .reg : elle s'écrit
    dans le CHEMIN, en insérant « WOW6432Node » après « Software ». C'est la
    seule forme que regedit comprenne.

    Lève `ValueError` sur une entrée non validée. `ecrire_valeurs` filtre déjà
    en amont, et le catalogue une seconde fois au parsing — mais une fonction
    qui fabrique un fichier importé avec les droits administrateur ne doit pas
    pouvoir produire une injection en silence parce qu'un appelant a oublié de
    vérifier. Elle refuse bruyamment plutôt que d'être complice.
    """
    raison = refus_de_cle(ruche, cle)
    if raison is not None:
        raise ValueError("clé de registre refusée (%s) : %r" % (raison, cle))
    for nom, valeur in valeurs.items():
        raison = refus_de_valeur(nom, valeur)
        if raison is not None:
            raise ValueError("valeur de registre refusée (%s) : %r" % (raison, nom))
    segments = [s for s in cle.replace("/", "\\").split("\\") if s]
    # Ne pas doubler WOW6432Node si le catalogue l'a déjà écrit dans le chemin :
    # on créerait « SOFTWARE\WOW6432Node\WOW6432Node\… », une clé fantôme que le
    # jeu ne lira jamais — et l'échec serait SILENCIEUX.
    deja_redirige = any(seg.lower() == "wow6432node" for seg in segments)
    if vue == 32 and not deja_redirige:
        segments = [segments[0], "WOW6432Node", *segments[1:]]
    lignes = ["Windows Registry Editor Version 5.00", "",
              "[%s\\%s]" % (_RUCHES_LONGUES[ruche], "\\".join(segments))]
    for nom, valeur in valeurs.items():
        if isinstance(valeur, int):
            lignes.append('"%s"=dword:%08x' % (_echappe_reg(nom), valeur))
        else:
            lignes.append('"%s"="%s"' % (_echappe_reg(nom), _echappe_reg(valeur)))
    lignes.append("")
    return "\r\n".join(lignes)


def lire_valeurs(ruche: str, cle: str, noms, vue: int = 32) -> dict:
    """Valeurs nommées actuellement en place. Lire ne demande AUCUN privilège.

    Retourne les seules valeurs trouvées : une clé absente n'est pas une erreur,
    c'est simplement « rien à comparer ».
    """
    if ruche not in RUCHES:
        return {}
    if sys.platform != "win32":
        # Le registre du préfixe est du texte : on le lit sans lancer Wine.
        from src.core import compat
        pfx = compat.prefixe()
        return compat.lire_valeurs(pfx, ruche, cle, noms, vue) if compat.pret(pfx) else {}
    import winreg

    ruches = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    acces = winreg.KEY_WOW64_32KEY if vue == 32 else winreg.KEY_WOW64_64KEY
    trouve: dict = {}
    try:
        with winreg.OpenKey(ruches[ruche], cle, 0, winreg.KEY_READ | acces) as k:
            for nom in noms:
                try:
                    trouve[nom] = winreg.QueryValueEx(k, nom)[0]
                except OSError:
                    pass
    except OSError:
        return {}
    return trouve


def comparer(ruche: str, cle: str, valeurs: dict, vue: int = 32) -> dict:
    """Ce qui DIFFÈRE entre le registre et ce qu'on veut y poser.

    Rend `{nom: (actuel, voulu)}`, limité aux valeurs qui ne concordent pas ;
    `actuel` vaut None quand la valeur n'est pas là du tout. Vide = rien à
    faire.

    Cette comparaison existait déjà, mais elle ne rendait qu'un booléen : on
    savait qu'il fallait écrire, jamais PAR-DESSUS QUOI. Or c'est le cas normal
    et non l'exception — l'installeur EA laisse un `Locale` et un `Install Dir`
    qui pointent sur son installation à lui, et sur la partie 2 son `fr_FR`
    n'est même pas une valeur que le jeu accepte. Remplacer sans le dire, c'est
    modifier le réglage de quelqu'un dans son dos ; le montrer, c'est la moitié
    utile du message de prévenance.
    """
    actuel = lire_valeurs(ruche, cle, list(valeurs), vue)
    return {nom: (actuel.get(nom), voulu)
            for nom, voulu in valeurs.items()
            if actuel.get(nom) != voulu}


def deja_a_jour(ruche: str, cle: str, valeurs: dict, vue: int = 32) -> bool:
    """True si le registre porte DÉJÀ exactement ces valeurs.

    C'est ce qui évite une demande d'élévation à chaque lancement : le cas
    courant, de très loin, est que rien n'a bougé depuis la dernière fois.
    """
    return not comparer(ruche, cle, valeurs, vue)


def _ecrire_direct(ruche: str, cle: str, valeurs: dict, vue: int) -> bool:
    """Écriture sans élévation. Suffit pour HKCU, et pour HKLM si déjà élevé.

    Sous Linux, il n'y a pas d'accès direct au registre d'un préfixe : Wine
    le tient en mémoire tant que son serveur tourne, et réécrire ses fichiers
    à côté serait écrasé à son arrêt. Tout passe par `_ecrire_eleve`.
    """
    if sys.platform != "win32":
        return False
    import winreg

    ruches = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    acces = winreg.KEY_WOW64_32KEY if vue == 32 else winreg.KEY_WOW64_64KEY
    try:
        with winreg.CreateKeyEx(ruches[ruche], cle, 0, winreg.KEY_WRITE | acces) as k:
            for nom, valeur in valeurs.items():
                type_ = winreg.REG_DWORD if isinstance(valeur, int) else winreg.REG_SZ
                winreg.SetValueEx(k, nom, 0, type_, valeur)
        return True
    except OSError as exc:
        log.info("Écriture directe refusée (%s) — passage par l'élévation", exc)
        return False


def _ecrire_eleve(ruche: str, cle: str, valeurs: dict, vue: int) -> bool:
    """Écriture élevée : .reg + « regedit /s » derrière une invite UAC.

    Le fichier est en UTF-16 avec BOM, seul encodage que regedit accepte pour le
    format « Version 5.00 » — et le seul qui tienne un chemin ou une valeur
    accentués. Rien n'est déduit de regedit lui-même : en mode silencieux il ne
    dit rien, même en échec. C'est la RELECTURE qui fait foi (`ecrire_valeurs`).

    Sous Linux, le même `.reg` part dans le préfixe (`_ecrire_par_wine`).
    """
    if sys.platform != "win32":
        return _ecrire_par_wine(ruche, cle, valeurs, vue)
    import ctypes

    # Dossier temporaire à nom ALÉATOIRE, et non un chemin fixe dans %TEMP%.
    # Ce fichier est importé par un regedit ÉLEVÉ : sous un nom prévisible, un
    # programme tournant sous le même compte — donc sans le moindre privilège —
    # pouvait le remplacer entre l'écriture et l'import, et faire exécuter son
    # contenu avec les droits administrateur. `mkdtemp` crée le dossier en accès
    # restreint, sous un nom qui ne se devine pas.
    dossier = Path(tempfile.mkdtemp(prefix="accio_reg_"))
    fichier = dossier / "langue.reg"
    _dossiers_a_nettoyer.append(dossier)
    try:
        fichier.write_text(construire_reg(ruche, cle, valeurs, vue), encoding="utf-16")
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "regedit.exe", '/s "%s"' % fichier, None, 0)
        if rc <= 32:
            # 5 = SE_ERR_ACCESSDENIED : l'utilisateur a refusé l'invite UAC.
            log.info("Élévation refusée ou impossible (ShellExecuteW=%d)", rc)
            return False
        return True
    except OSError as exc:
        log.warning("Écriture élevée impossible : %s", exc)
        return False


# Délai maximal d'un import par le lanceur de compatibilité. umu démarre le
# conteneur du Steam Linux Runtime avant Proton : quelques secondes d'habitude.
_DELAI_REGEDIT_WINE_S = 120


def _ecrire_par_wine(ruche: str, cle: str, valeurs: dict, vue: int) -> bool:
    r"""Importe le `.reg` dans le registre du préfixe, par `regedit /S`.

    Vérifié sur un préfixe Wine 9.0 (2026-09-24) : l'import prend 0,5 s, et
    le fichier `system.reg` n'est réécrit qu'à l'arrêt du wineserver, deux à
    trois secondes plus tard — d'où l'attente de `ecrire_valeurs`, qui relit
    jusqu'à ce que ce soit vrai. Le `.reg` est posé DANS le préfixe
    (`C:\windows\temp`) : c'est un chemin que tout préfixe connaît, sans
    dépendre du lecteur `Z:`.
    """
    from src.core import compat

    lanceur = compat.lanceur()
    pfx = compat.prefixe()
    if lanceur is None or not compat.pret(pfx):
        return False
    try:
        temp = pfx / "drive_c" / "windows" / "temp"
        temp.mkdir(parents=True, exist_ok=True)
        dossier = Path(tempfile.mkdtemp(prefix="accio_reg_", dir=temp))
        _dossiers_a_nettoyer.append(dossier)
        fichier = dossier / "langue.reg"
        fichier.write_text(construire_reg(ruche, cle, valeurs,
                                          compat.vue_effective(pfx, ruche, vue)),
                           encoding="utf-16")
        env = compat.environnement(lanceur, pfx)
        # La fenêtre attend : pas de mise à jour du runtime d'umu maintenant.
        env.setdefault("UMU_RUNTIME_UPDATE", "0")
        commande = compat.commande_regedit(lanceur, pfx, compat.chemin_windows(fichier, pfx))
        log.info("Import du registre dans le préfixe : %s", " ".join(commande))
        # Lanceur trouvé par chemin ABSOLU (`compat._trouver`), fichier .reg
        # construit et validé par `construire_reg` ; liste d'arguments, aucun shell.
        subprocess.run(commande, env=env, stdin=subprocess.DEVNULL,  # nosec B603
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=_DELAI_REGEDIT_WINE_S, check=False)
        return True
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log.warning("Import du registre dans le préfixe impossible : %s", exc)
        return False


# Dossiers temporaires à retirer une fois regedit passé. On ne les supprime pas
# tout de suite : `regedit /s` rend la main AVANT d'avoir lu le fichier, et
# l'effacer trop tôt ferait échouer l'import sans un mot.
_dossiers_a_nettoyer: list = []


def _nettoyer_reg() -> None:
    """Retire les .reg temporaires et leur dossier."""
    import shutil

    while _dossiers_a_nettoyer:
        shutil.rmtree(_dossiers_a_nettoyer.pop(), ignore_errors=True)


def ecrire_valeurs(ruche: str, cle: str, valeurs: dict, vue: int = 32,
                   attente_s: float | None = None, confirmer=None) -> bool:
    """Pose les valeurs et VÉRIFIE qu'elles y sont. False si ça n'a pas pris.

    Ne fait rien — et surtout ne demande aucune élévation — si le registre porte
    déjà ces valeurs. Toute entrée refusée par `refus_de_cle` / `refus_de_valeur`
    fait échouer l'opération ENTIÈRE : un catalogue distant ne compose pas une
    écriture registre à moitié.

    `confirmer(ruche, cle, valeurs, ecarts)` est appelé JUSTE AVANT l'écriture,
    et seulement quand il y en a réellement une à faire. `ecarts` est ce que
    rend `comparer()` : il porte la valeur ACTUELLE de chaque entrée qu'on
    s'apprête à écraser, pour que la question posée à l'utilisateur dise par
    quoi on remplace quoi. Modifier le registre de
    quelqu'un sans le lui dire ne se fait pas, et sous HKLM ça enchaîne en plus
    sur une invite UAC : voir Windows demander une autorisation sans savoir
    pourquoi, c'est la refuser. Le rappel arrive donc au plus près du geste, et
    jamais pour rien — au deuxième lancement le registre est déjà bon et
    personne n'est dérangé. Retourner False annule proprement (False global).

    `attente_s` borne la relecture : 6 s sous Windows, 20 s sous Wine, où le
    registre n'arrive sur le disque qu'à l'arrêt du wineserver.
    """
    if not disponible():
        return False
    if attente_s is None:
        attente_s = 6.0 if sys.platform == "win32" else 20.0
    raison = refus_de_cle(ruche, cle)
    if raison is not None:
        log.warning("Clé de registre refusée (%s) : %s\\%s", raison, ruche, cle)
        return False
    for nom, valeur in valeurs.items():
        raison = refus_de_valeur(nom, valeur)
        if raison is not None:
            log.warning("Valeur de registre refusée (%s) : %r", raison, nom)
            return False
    if not valeurs:
        return True
    ecarts = comparer(ruche, cle, valeurs, vue)
    if not ecarts:
        return True
    for nom, (actuel, voulu) in ecarts.items():
        log.info("Registre à corriger — %s : %r → %r", nom, actuel, voulu)
    if confirmer is not None and not confirmer(ruche, cle, valeurs, ecarts):
        log.info("Écriture registre refusée par l'utilisateur : %s\\%s", ruche, cle)
        return False

    if _ecrire_direct(ruche, cle, valeurs, vue):
        return deja_a_jour(ruche, cle, valeurs, vue)
    try:
        if not _ecrire_eleve(ruche, cle, valeurs, vue):
            return False
        # regedit rend la main avant d'avoir fini : on relit jusqu'à ce que ce
        # soit vrai, plutôt que de dormir un temps arbitraire et d'espérer.
        # Sous Wine, chaque relecture reparse un `system.reg` de plusieurs Mo :
        # un pas plus long, pour une attente qui l'est aussi.
        import time
        pas = 0.15 if sys.platform == "win32" else 0.5
        limite = time.monotonic() + attente_s
        while time.monotonic() < limite:
            if deja_a_jour(ruche, cle, valeurs, vue):
                return True
            time.sleep(pas)
    finally:
        _nettoyer_reg()
    log.warning("Le registre n'a pas pris les valeurs attendues : %s\\%s", ruche, cle)
    return False
