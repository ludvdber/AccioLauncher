"""Progression sur l'icône de la barre des tâches Windows (ITaskbarList3, COM/ctypes).

Affiche la barre verte de progression sur l'icône du launcher pendant les
téléchargements/installations — comme les navigateurs ou Steam. Aucun module
tiers : appels COM bruts via ctypes. No-op silencieux hors Windows (objectif
Linux) ou si l'init COM échoue.
"""

import logging
import sys

log = logging.getLogger(__name__)

# TBPFLAG (SetProgressState)
TBPF_NOPROGRESS = 0x0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL = 0x2
TBPF_ERROR = 0x4
TBPF_PAUSED = 0x8

_CLSID_TASKBAR_LIST = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
_IID_ITASKBAR_LIST3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"

# Index vtable d'ITaskbarList3 (hérite ITaskbarList/2) :
# 0-2 IUnknown · 3 HrInit · 4-7 ITaskbarList · 8 MarkFullscreenWindow
# 9 SetProgressValue · 10 SetProgressState
_VTBL_HRINIT = 3
_VTBL_SET_PROGRESS_VALUE = 9
_VTBL_SET_PROGRESS_STATE = 10


class TaskbarProgress:
    """Pilote la progression de l'icône taskbar pour un HWND donné."""

    def __init__(self, hwnd: int) -> None:
        self._hwnd = hwnd
        self._iface = None
        if sys.platform != "win32" or not hwnd:
            return
        try:
            self._init_com()
        except Exception as exc:  # COM peut échouer de mille façons — jamais bloquant
            log.debug("TaskbarProgress indisponible : %s", exc)
            self._iface = None

    # ── Plomberie COM ──

    def _init_com(self) -> None:
        import ctypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)

        clsid, iid = _GUID(), _GUID()
        ole32.CLSIDFromString(_CLSID_TASKBAR_LIST, ctypes.byref(clsid))
        ole32.CLSIDFromString(_IID_ITASKBAR_LIST3, ctypes.byref(iid))

        iface = ctypes.c_void_p()
        CLSCTX_INPROC_SERVER = 1
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER,
            ctypes.byref(iid), ctypes.byref(iface),
        )
        if hr != 0 or not iface.value:
            raise OSError(f"CoCreateInstance(ITaskbarList3) → HRESULT {hr:#010x}")
        self._iface = iface

        hr = self._method(_VTBL_HRINIT)(self._iface)
        if hr != 0:
            raise OSError(f"ITaskbarList3.HrInit → HRESULT {hr:#010x}")

    def _method(self, index: int, *argtypes):
        """Résout la méthode `index` de la vtable COM en callable ctypes."""
        import ctypes

        vtable = ctypes.cast(
            ctypes.c_void_p(
                ctypes.cast(self._iface, ctypes.POINTER(ctypes.c_void_p))[0]
            ),
            ctypes.POINTER(ctypes.c_void_p),
        )
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
        return proto(vtable[index])

    # ── API publique (no-op si init échouée) ──

    def set_progress(self, done: int, total: int) -> None:
        """Affiche la progression (barre verte sur l'icône taskbar)."""
        if self._iface is None or total <= 0:
            return
        import ctypes
        try:
            self._method(
                _VTBL_SET_PROGRESS_VALUE,
                ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_ulonglong,
            )(self._iface, self._hwnd, done, total)
        except Exception as exc:
            log.debug("SetProgressValue : %s", exc)

    def set_state(self, state: int) -> None:
        if self._iface is None:
            return
        import ctypes
        try:
            self._method(_VTBL_SET_PROGRESS_STATE, ctypes.c_void_p, ctypes.c_int)(
                self._iface, self._hwnd, state,
            )
        except Exception as exc:
            log.debug("SetProgressState : %s", exc)

    def clear(self) -> None:
        """Retire la barre de progression de l'icône."""
        self.set_state(TBPF_NOPROGRESS)
