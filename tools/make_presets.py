"""Genera i preset audio versionati nel repo.

Sono tutti procedurali (white/pink/brown noise + filtri) → zero copyright,
file piccoli (~3-5 MB ognuno per 10 minuti in Opus a 96 kbps), loopabili
(fade-in/fade-out brevi sugli estremi per evitare click).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "audio"
OUT.mkdir(exist_ok=True)


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    # winget install location for yt-dlp.FFmpeg
    candidates = list(
        Path(os.environ.get("LOCALAPPDATA", "")).glob(
            "Microsoft/WinGet/Packages/yt-dlp.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"
        )
    )
    if candidates:
        return str(candidates[0])
    raise RuntimeError("ffmpeg non trovato. Installa con `winget install yt-dlp.FFmpeg`.")


FFMPEG = find_ffmpeg()


def run(args: list[str]) -> None:
    print(">", " ".join(args))
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


DURATION = 600  # 10 minuti
BITRATE = "96k"   # opus 96 kbps è già trasparente per il noise

# (nome_file, descrizione_filter)
PRESETS = [
    # Phon (white noise) — suono asciugacapelli classico
    ("phon.opus",
     "anoisesrc=color=white:duration={d}:amplitude=0.4,"
     "highpass=f=200,lowpass=f=8000,"
     "afade=t=in:st=0:d=1,afade=t=out:st={fo}:d=1"),

    # Phon dolce (pink noise) — più rilassante
    ("phon2.opus",
     "anoisesrc=color=pink:duration={d}:amplitude=0.5,"
     "afade=t=in:st=0:d=1,afade=t=out:st={fo}:d=1"),

    # Drone (brown noise) — basso e ronzio caldo, tipo refrigeratore
    ("drone.opus",
     "anoisesrc=color=brown:duration={d}:amplitude=0.7,"
     "afade=t=in:st=0:d=1,afade=t=out:st={fo}:d=1"),

    # Pioggia simulata: white noise filtrato per imitare le gocce
    ("pioggia.opus",
     "anoisesrc=color=white:duration={d}:amplitude=0.5,"
     "highpass=f=1500,lowpass=f=12000,"
     "tremolo=f=8:d=0.3,"
     "afade=t=in:st=0:d=1,afade=t=out:st={fo}:d=1"),
]


def main() -> None:
    fade_out_start = DURATION - 1
    for name, filt_tpl in PRESETS:
        out = OUT / name
        filt = filt_tpl.format(d=DURATION, fo=fade_out_start)
        run([
            FFMPEG, "-y", "-f", "lavfi", "-i", filt,
            "-ac", "2", "-ar", "48000",
            "-c:a", "libopus", "-b:a", BITRATE,
            "-application", "audio",
            str(out),
        ])
        kb = out.stat().st_size / 1024
        print(f"  -> {out.name} ({kb:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())
