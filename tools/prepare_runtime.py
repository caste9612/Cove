"""Prepara la cartella runtime/ con Python embedded + PySide6 + yt-dlp.

Eseguito una volta (e ogni volta che si aggiornano le dipendenze).
runtime/ va versionato nel repo per build riproducibili e installazione
veloce per gli utenti finali.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"

# Python 3.11.9 embeddable (stabile, supportato da PySide6)
PY_VER = "3.11.9"
EMBED_URL = f"https://www.python.org/ftp/python/{PY_VER}/python-{PY_VER}-embed-amd64.zip"

# Pacchetti runtime
RUNTIME_REQS = [
    "PySide6==6.10.*",
    "yt-dlp",
]

# Pacchetti / cartelle da rimuovere dopo l'install per ridurre dimensione
PRUNE_DIRS = [
    "PyInstaller", "PyInstaller-*.dist-info", "pyinstaller_hooks_contrib",
    "pyinstaller_hooks_contrib-*.dist-info",
    "PIL", "pillow-*.dist-info",
    "pip", "pip-*.dist-info",
    "setuptools", "setuptools-*.dist-info", "pkg_resources", "_distutils_hack",
]

PRUNE_QT_MODULES = [
    "Qt63D*", "Qt6Bluetooth*", "Qt6Charts*", "Qt6Concurrent*", "Qt6Data*",
    "Qt6DBus*", "Qt6Designer*", "Qt6Graphs*", "Qt6Help*", "Qt6HttpServer*",
    "Qt6Labs*", "Qt6Location*", "Qt6NetworkAuth*", "Qt6Nfc*", "Qt6OpenGL*",
    "Qt6Pdf*", "Qt6Positioning*", "Qt6PrintSupport*", "Qt6Qml*", "Qt6Quick*",
    "Qt6RemoteObjects*", "Qt6Scxml*", "Qt6Sensors*", "Qt6Serial*",
    "Qt6ShaderTools*", "Qt6SpatialAudio*", "Qt6Sql*", "Qt6StateMachine*",
    "Qt6Test*", "Qt6TextToSpeech*", "Qt6UiTools*", "Qt6VirtualKeyboard*",
    "Qt6Web*",
    "QtBluetooth*", "QtCharts*", "QtConcurrent*", "QtData*", "QtDBus*",
    "QtDesigner*", "QtGraphs*", "QtHelp*", "QtHttpServer*", "QtLabs*",
    "QtLocation*", "QtNetworkAuth*", "QtNfc*", "QtOpenGL*", "QtPdf*",
    "QtPositioning*", "QtPrintSupport*", "QtQml*", "QtQuick*",
    "QtRemoteObjects*", "QtScxml*", "QtSensors*", "QtSerial*",
    "QtSpatial*", "QtSql*", "QtStateMachine*", "QtTest*",
    "QtTextToSpeech*", "QtUiTools*", "QtVirtualKeyboard*", "QtWeb*", "Qt3D*",
]

PRUNE_PLUGINS = [
    "webview", "virtualkeyboard", "sqldrivers", "sceneparsers",
    "renderplugins", "printsupport", "position", "playlistformats",
    "assetimporters", "3dinputdevices", "designer", "geometryloaders",
    "qmltooling", "geoservices",
]


def download_embed() -> Path:
    print(f"Scarico {EMBED_URL} ...")
    dst = ROOT / "build" / f"python-{PY_VER}-embed.zip"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        with urllib.request.urlopen(EMBED_URL) as r:
            dst.write_bytes(r.read())
    return dst


def extract_embed(zip_path: Path) -> None:
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    RUNTIME.mkdir()
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(RUNTIME)
    # Abilita site-packages
    pth = RUNTIME / "python311._pth"
    pth.write_text("python311.zip\n.\nLib\\site-packages\n\nimport site\n", encoding="ascii")


def install_pip() -> None:
    """Installa pip nel runtime embedded scaricando get-pip.py."""
    get_pip = ROOT / "build" / "get-pip.py"
    if not get_pip.exists():
        with urllib.request.urlopen("https://bootstrap.pypa.io/get-pip.py") as r:
            get_pip.write_bytes(r.read())
    subprocess.run([str(RUNTIME / "python.exe"), str(get_pip), "--no-warn-script-location"], check=True)


def install_packages() -> None:
    site_pkgs = RUNTIME / "Lib" / "site-packages"
    site_pkgs.mkdir(parents=True, exist_ok=True)
    args = [str(RUNTIME / "python.exe"), "-m", "pip", "install",
            "--no-warn-script-location", "--no-cache-dir"]
    subprocess.run(args + RUNTIME_REQS, check=True)


def prune() -> None:
    site_pkgs = RUNTIME / "Lib" / "site-packages"
    pyside = site_pkgs / "PySide6"
    for pat in PRUNE_DIRS:
        for p in site_pkgs.glob(pat):
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    if pyside.exists():
        for pat in PRUNE_QT_MODULES:
            for p in pyside.glob(pat):
                if p.is_file():
                    p.unlink(missing_ok=True)
                else:
                    shutil.rmtree(p, ignore_errors=True)
        plugins_dir = pyside / "plugins"
        for name in PRUNE_PLUGINS:
            p = plugins_dir / name
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)


def main() -> None:
    zip_path = download_embed()
    extract_embed(zip_path)
    install_pip()
    install_packages()
    prune()
    sz = sum(p.stat().st_size for p in RUNTIME.rglob("*") if p.is_file())
    print(f"\nruntime/ pronto, totale {sz / (1024**2):.1f} MB")


if __name__ == "__main__":
    main()
