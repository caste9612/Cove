"""Orchestra il build di Cove.

Schema:
- Cove.exe è un wrapper leggero (PyInstaller --onefile, no Qt) che lancia
  runtime/pythonw.exe app.py. Nessun bug DLL conflitti.
- runtime/  contiene il Python embedded ufficiale + PySide6 + yt-dlp
  (preparato in cartella runtime/ del repo).
- app.py, icon.ico, audio/ stanno accanto a Cove.exe.

Uso:
    python tools\\build.py              # build tutto in dist/Cove/
    python tools\\build.py --installer  # ...e crea l'installer Inno
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "Cove"
BUILD = ROOT / "build"
VERSION_FILE = ROOT / "VERSION"


def read_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    return "0.0.0"


def run(args, **kw) -> None:
    print(">", " ".join(str(a) for a in args))
    subprocess.run(args, check=True, **kw)


def clean() -> None:
    for d in (DIST.parent, BUILD):
        if d.exists():
            print(f"  rimuovo {d}")
            shutil.rmtree(d, ignore_errors=True)


def check_runtime() -> None:
    rt = ROOT / "runtime"
    pyw = rt / "pythonw.exe"
    pyside = rt / "Lib" / "site-packages" / "PySide6"
    if not pyw.exists() or not pyside.exists():
        sys.exit(
            "Manca runtime/ con Python embedded + PySide6.\n"
            "Esegui prima:  python tools\\prepare_runtime.py"
        )


def build_launcher() -> None:
    """Compila launcher.py → dist/Cove/Cove.exe (onefile, no console)."""
    DIST.mkdir(parents=True, exist_ok=True)
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--noconsole", "--noconfirm", "--clean",
        "--name", "Cove",
        "--icon", str(ROOT / "icon.ico"),
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "launcher"),
        "--specpath", str(BUILD / "launcher"),
        str(ROOT / "launcher.py"),
    ])


def copy_payload() -> None:
    items = [
        ("app.py", DIST / "app.py"),
        ("icon.ico", DIST / "icon.ico"),
        ("audio", DIST / "audio"),
        ("runtime", DIST / "runtime"),
    ]
    for src_rel, dst in items:
        src = ROOT / src_rel
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        print(f"  -> {dst.relative_to(ROOT)}")


def inno_setup() -> None:
    import os
    iscc_candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    iscc = next((p for p in iscc_candidates if p.exists()), None)
    if not iscc:
        sys.exit("Inno Setup non trovato. Installa con: winget install JRSoftware.InnoSetup")
    run([str(iscc), f"/DAppVersion={read_version()}", "cove.iss"], cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", action="store_true")
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()

    print(f"== Build Cove v{read_version()} ==")
    check_runtime()
    if not args.no_clean:
        clean()
    print("\n[1] Launcher Cove.exe...")
    build_launcher()
    print("\n[2] Copia payload (runtime, app.py, audio, icon)...")
    copy_payload()
    if args.installer:
        print("\n[3] Inno Setup installer...")
        inno_setup()
    # report dimensione
    sz = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"\nFatto. dist/Cove totale: {sz / (1024**2):.1f} MB")


if __name__ == "__main__":
    main()
