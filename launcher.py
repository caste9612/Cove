"""Cove.exe — wrapper che lancia il Python embedded con app.py.
Nessuna dipendenza Qt: PyInstaller bundla solo stdlib, niente DLL conflicts."""
import os
import subprocess
import sys

if getattr(sys, "frozen", False):
    base = os.path.dirname(os.path.abspath(sys.executable))
else:
    base = os.path.dirname(os.path.abspath(__file__))

python = os.path.join(base, "runtime", "pythonw.exe")
script = os.path.join(base, "app.py")

if not os.path.exists(python):
    import ctypes
    ctypes.windll.user32.MessageBoxW(
        0, f"Manca {python}.\nReinstalla Cove.", "Cove — Errore", 0x10
    )
    sys.exit(1)

# DETACHED_PROCESS + CREATE_NO_WINDOW così il wrapper esce subito
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000
subprocess.Popen(
    [python, script],
    cwd=base,
    creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
    close_fds=True,
)
