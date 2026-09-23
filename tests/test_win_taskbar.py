"""La progression sur l'icône de la barre des tâches — ce module n'avait AUCUN test.

Relevé par l'audit du 2026-09-23 : 121 lignes d'appels COM bruts en ctypes,
jamais exercées. C'est précisément le genre de code qu'on ne teste pas « parce
qu'il faut Windows et une vraie fenêtre » — alors que tout ce qui compte ici
s'exerce sans l'un ni l'autre : les gardes (pas de HWND, hors Windows, init
ratée, total nul) et le fait que chaque méthode publique vise la BONNE entrée
de vtable avec les BONS arguments.

Rien n'appelle le vrai COM : `_method` est remplacé par un espion. Un test qui
créerait une vraie `ITaskbarList3` poserait une barre de progression sur
l'icône de la personne qui lance la suite.
"""

import sys

from src.core import win_taskbar
from src.core.win_taskbar import (
    TBPF_ERROR, TBPF_INDETERMINATE, TBPF_NOPROGRESS, TBPF_NORMAL, TBPF_PAUSED,
    TaskbarProgress, _VTBL_SET_PROGRESS_STATE, _VTBL_SET_PROGRESS_VALUE,
)


def _espionne(objet) -> list[tuple]:
    """Remplace `_method` par un mouchard ; rend la liste des appels.

    Sur l'INSTANCE et jamais sur la classe : `TaskbarProgress` n'est pas un
    type sip, mais la règle du projet vaut aussi pour les objets ordinaires —
    un attribut de classe « restauré » après un test est la façon dont cette
    suite s'est déjà fait tuer plusieurs fichiers plus loin.
    """
    appels: list[tuple] = []

    def faux_method(index, *argtypes):
        def appel(*args):
            appels.append((index, args))
            return 0
        return appel

    objet._method = faux_method
    return appels


class TestLesGardes:
    """Aucune de ces situations ne doit lever : une barre de progression
    décorative n'a pas le droit d'interrompre un téléchargement."""

    def test_sans_hwnd_rien_n_est_initialise(self):
        barre = TaskbarProgress(0)
        assert barre._iface is None

    def test_sans_hwnd_les_methodes_ne_levent_pas(self):
        barre = TaskbarProgress(0)
        barre.set_progress(50, 100)
        barre.set_state(TBPF_NORMAL)
        barre.clear()

    def test_hors_windows_rien_n_est_tente(self, monkeypatch):
        """Objectif Linux : le module doit être inerte, pas absent."""
        monkeypatch.setattr(sys, "platform", "linux")
        appels = []
        monkeypatch.setattr(TaskbarProgress, "_init_com",
                            lambda self: appels.append(1))
        barre = TaskbarProgress(12345)
        assert barre._iface is None
        assert not appels, "COM a été tenté hors Windows"

    def test_un_echec_d_init_ne_remonte_jamais(self, monkeypatch):
        """« COM peut échouer de mille façons » : le launcher doit survivre à
        toutes, y compris à celles qu'on n'a pas prévues."""
        monkeypatch.setattr(sys, "platform", "win32")

        def explose(self):
            raise OSError("CoCreateInstance a échoué")

        monkeypatch.setattr(TaskbarProgress, "_init_com", explose)
        barre = TaskbarProgress(12345)
        assert barre._iface is None
        barre.set_progress(1, 2)        # ne lève pas non plus

    def test_un_appel_com_qui_echoue_ne_remonte_pas(self):
        barre = TaskbarProgress(0)
        barre._iface = object()          # fait croire à une init réussie

        def method_qui_explose(index, *argtypes):
            def appel(*args):
                raise OSError("l'interface est morte")
            return appel

        barre._method = method_qui_explose
        barre.set_progress(1, 2)
        barre.set_state(TBPF_NORMAL)


class TestCeQuiPartVersWindows:
    """La barre vise-t-elle la bonne méthode, avec les bons arguments ?"""

    @staticmethod
    def _barre():
        barre = TaskbarProgress(0)
        barre._iface = object()
        barre._hwnd = 4242
        return barre, _espionne(barre)

    def test_set_progress_transmet_hwnd_puis_avancement(self):
        barre, appels = self._barre()
        barre.set_progress(30, 120)
        assert len(appels) == 1
        index, args = appels[0]
        assert index == _VTBL_SET_PROGRESS_VALUE
        assert args == (barre._iface, 4242, 30, 120)

    def test_un_total_nul_n_envoie_rien(self):
        """`SetProgressValue(done, 0)` est une division par zéro côté Windows.
        Le cas arrive pour de vrai : la taille d'une archive n'est connue
        qu'après la réponse du serveur."""
        barre, appels = self._barre()
        barre.set_progress(10, 0)
        barre.set_progress(10, -1)
        assert appels == []

    def test_set_state_transmet_l_etat(self):
        barre, appels = self._barre()
        barre.set_state(TBPF_ERROR)
        index, args = appels[0]
        assert index == _VTBL_SET_PROGRESS_STATE
        assert args == (barre._iface, 4242, TBPF_ERROR)

    def test_clear_retire_la_barre(self):
        """`clear()` doit envoyer NOPROGRESS, pas simplement 0 % — une barre à
        0 % reste une barre affichée."""
        barre, appels = self._barre()
        barre.clear()
        assert appels[0][0] == _VTBL_SET_PROGRESS_STATE
        assert appels[0][1][2] == TBPF_NOPROGRESS


class TestLesConstantesNeDerivent:
    """Ces valeurs sont imposées par Windows, pas choisies par nous.

    Une faute de frappe dedans ne lève rien et ne se voit pas : on afficherait
    simplement le mauvais état — une barre rouge pendant un téléchargement qui
    va bien, ou rien du tout pendant qu'il avance.
    """

    def test_les_drapeaux_tbpf_sont_ceux_de_l_api(self):
        assert (TBPF_NOPROGRESS, TBPF_INDETERMINATE, TBPF_NORMAL,
                TBPF_ERROR, TBPF_PAUSED) == (0x0, 0x1, 0x2, 0x4, 0x8)

    def test_les_index_de_vtable_sont_distincts(self):
        """L'ordre de la vtable d'ITaskbarList3 est fixé par l'interface :
        deux index égaux appelleraient la même méthode pour deux gestes."""
        index = (win_taskbar._VTBL_HRINIT, _VTBL_SET_PROGRESS_VALUE,
                 _VTBL_SET_PROGRESS_STATE)
        assert len(set(index)) == len(index)
        assert index == (3, 9, 10)
