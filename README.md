# Cove

App minimale per Windows che scarica audio da YouTube alla massima qualità e lo riproduce in un mini-player integrato. Pensata per audio di concentrazione: rumore bianco, drone, pioggia, lofi, ambient.

<p align="center"><img src="icon.png" width="160"></p>

## Caratteristiche

- **Tray icon** nella barra di sistema: click → pannello scorrevole in basso a destra
- **Download audio YouTube** alla massima qualità (Opus nativo, ~160 kbps, zero riconversione)
- **Mini-player integrato** (play / pausa / seek / volume) — niente apertura di altri programmi
- **Hotkey multimediali globali**: i tasti Play/Pausa delle cuffie controllano l'app
- **Libreria persistente**: tutti i file in `audio/` sono sempre disponibili nel pannello
- **Preset inclusi**: 4 audio procedurali (phon, phon2, drone, pioggia) generati con ffmpeg
- **Auto-detect URL da clipboard** all'apertura del pannello
- **Tutto in cartella di installazione** — niente sparso in `Music`/`AppData`

## Installazione (utente finale)

1. Scarica `Cove-Setup-X.Y.Z.exe` dall'ultima [Release](https://github.com/caste9612/Cove/releases)
2. Esegui — installa in `%LOCALAPPDATA%\Programs\Cove` senza richiedere privilegi admin
3. Opzionale: spunta "Avvia all'accesso a Windows"

## Sviluppo

Prerequisiti:
- Windows 10/11 64-bit
- Python 3.11 ufficiale (NON Anaconda; vedi `tools/prepare_runtime.py`)
- [Inno Setup 6](https://jrsoftware.org/isdl.php) per buildare l'installer (`winget install JRSoftware.InnoSetup`)
- ffmpeg (per rigenerare i preset audio): `winget install yt-dlp.FFmpeg`

```powershell
# venv di sviluppo
py -3.11 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# avvio diretto (dev)
python app.py

# build runtime embedded (1 volta + dopo update dipendenze)
python tools\prepare_runtime.py

# build installer
python tools\build.py --installer
# → dist\Cove-Setup-X.Y.Z.exe

# rigenera preset audio
python tools\make_presets.py

# rigenera icona
python tools\make_icon.py
```

## Struttura

```
Cove/
├── app.py                # app principale (PySide6)
├── launcher.py           # wrapper compilato in Cove.exe
├── icon.ico / icon.png
├── audio/                # 4 preset noise + tutti i download (versionati)
├── runtime/              # Python embedded + PySide6 + yt-dlp (versionato)
├── tools/
│   ├── build.py          # orchestra build + installer
│   ├── prepare_runtime.py
│   ├── make_icon.py
│   └── make_presets.py
├── cove.iss              # script Inno Setup
└── VERSION
```

## Tecnica

- **Cove.exe** è un wrapper minimale (PyInstaller --onefile, no Qt) che lancia `runtime\pythonw.exe app.py`. Questo evita conflitti DLL su sistemi con Anaconda nel PATH (Anaconda mette versioni vecchie di msvcp140/concrt140 nel PATH globale, che entrano in collisione con PySide6 quando lo si bundla con PyInstaller direttamente).
- **runtime/** è una copia del Python embedded ufficiale + PySide6 + yt-dlp con i moduli Qt non usati rimossi (~305 MB invece di ~700 MB).
- **app.py** usa il backend FFmpeg di QtMultimedia per riprodurre Opus/WebM senza dipendere dai codec di Windows.
- **Hotkey globali** via `RegisterHotKey` + `QAbstractNativeEventFilter` su `WM_HOTKEY`.

## Licenza

MIT. Vedi `LICENSE`.
