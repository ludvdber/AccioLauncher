"""Arrêt d'un `QThread` à la FERMETURE — le seul moment où l'on n'a plus le temps.

En cours de session, un thread qui ne rend pas la main se **gare** : c'est ce que
font `GameOperations._zombies` et `UpdateDispatcher.shutdown_checker`, qui le
déparentent et attendent son `finished` natif. C'est la bonne réponse tant que
l'application vit, parce qu'on peut attendre indéfiniment sans gêner personne.

À la fermeture, non. Et le laisser vivre n'est pas une option neutre : Qt
DÉTRUIT le `QThread` en même temps que son parent, et détruire un thread qui
tourne encore **abandonne le processus** — code de sortie `0xC0000409`, aucun
message, aucun rapport de crash (c'est un abandon C++, il se produit sous Python
et `install_excepthook` ne le voit jamais). Reproduit le 2026-08-21 sur les deux
chemins de fermeture, avec la séquence exacte de `main.py`.

L'attente ne suffit pas : le `read` httpx est réglé à 120 s et l'annulation
n'est relue qu'entre deux morceaux, donc un serveur qui cesse d'envoyer laisse le
thread sourd pendant deux minutes. Attendre autant, c'est un launcher qui refuse
de se fermer ; attendre 3 s puis détruire, c'est le plantage ci-dessus.

D'où `terminate()`. Il est déconseillé en général — le thread est tué n'importe
où dans son code, sans libérer ses verrous — mais aucun de ces griefs ne tient
ici : le processus s'en va dans la milliseconde qui suit. Le seul dégât possible
est un `.part` tronqué, or c'est exactement ce que la reprise HTTP et la
vérification SHA-256 savent rattraper au lancement suivant.
"""

import logging

from PyQt6.QtCore import QThread

log = logging.getLogger(__name__)

# Temps laissé au thread pour s'arrêter de lui-même. Au-delà, il est bloqué sur
# un read réseau mort et n'a aucune raison de revenir avant le timeout de 120 s.
DELAI_GRACE_MS = 3000

# Temps laissé à `terminate()` pour aboutir. Court : l'appel est traité par
# l'ordonnanceur, pas par le code du thread.
DELAI_ARRET_MS = 2000


def arreter_a_la_fermeture(thread: QThread, nom: str) -> bool:
    """Arrête `thread` de façon BORNÉE. À n'appeler QUE depuis un `closeEvent`.

    L'annulation propre au thread (`cancel()`) doit avoir été demandée par
    l'appelant : elle seule sait ce qu'il faut poser comme drapeau. Retourne
    True si le thread est réellement arrêté — la valeur est utile aux tests,
    l'appelant n'a rien à en faire.
    """
    if not thread.isRunning():
        return True
    thread.requestInterruption()
    if thread.wait(DELAI_GRACE_MS):
        return True
    log.warning("%s encore actif à la fermeture — arrêt forcé", nom)
    thread.terminate()
    if not thread.wait(DELAI_ARRET_MS):
        log.error("%s n'a pas répondu à terminate() — fermeture à risque", nom)
        return False
    return True
