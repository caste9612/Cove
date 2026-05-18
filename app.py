"""
Cove — Tray app per scaricare audio YouTube alla massima qualità (Opus nativo)
e riprodurlo direttamente nel pannello. Pensato per audio di concentrazione
(rumore bianco, pioggia, drone ambient).
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Forziamo il backend FFmpeg di QtMultimedia per supportare Opus/WebM
# su Windows senza dipendere dai codec installati nel sistema.
os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

# ---- Logging a file fin dal boot (utile in build PyInstaller windowed,
# dove stdout/stderr non sono visibili). Cattura anche eccezioni non gestite.
def _early_log_setup() -> None:
    if getattr(sys, "frozen", False):
        log_dir = Path(sys.executable).resolve().parent
    else:
        log_dir = Path(__file__).resolve().parent
    log_path = log_dir / "cove.log"
    try:
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    import datetime
    log_file.write(f"\n=== {datetime.datetime.now().isoformat()} avvio Cove ===\n")
    # Redirigi stdout/stderr al file (Python "frozen" non ha console)
    sys.stdout = log_file
    sys.stderr = log_file
    def _hook(et, ev, tb):
        log_file.write("FATAL:\n")
        traceback.print_exception(et, ev, tb, file=log_file)
        log_file.flush()
        sys.__excepthook__(et, ev, tb)
    sys.excepthook = _hook

_early_log_setup()

# In bundle PyInstaller: evita che DLL di sistema (es. Anaconda nel PATH)
# vengano caricate al posto di quelle del bundle. Pre-carichiamo esplicitamente
# le MSVC redist DLL così, quando Qt6Core le richiede, Windows trova in memoria
# la versione corretta invece di andare a cercarne una più vecchia nel PATH.
if getattr(sys, "frozen", False):
    import ctypes
    _internal = Path(sys.executable).resolve().parent / "_internal"
    if _internal.exists():
        _dll_dirs = [_internal]
        for sub in ("PySide6", "shiboken6"):
            p = _internal / sub
            if p.exists():
                _dll_dirs.append(p)
        for d in _dll_dirs:
            try:
                os.add_dll_directory(str(d))
            except (OSError, AttributeError):
                pass
        os.environ["PATH"] = (
            os.pathsep.join(str(d) for d in _dll_dirs)
            + os.pathsep + os.environ.get("PATH", "")
        )
        # Pre-carica le DLL critiche per evitare collisioni con versioni più
        # vecchie già caricate dal loader. L'ordine è importante.
        _critical_dlls = [
            "VCRUNTIME140.dll", "VCRUNTIME140_1.dll",
            "MSVCP140.dll", "MSVCP140_1.dll", "MSVCP140_2.dll",
            "CONCRT140.dll",
        ]
        for name in _critical_dlls:
            for d in _dll_dirs:
                p = d / name
                if p.exists():
                    try:
                        ctypes.WinDLL(str(p))
                        print(f"[boot] preload OK: {p}", flush=True)
                    except OSError as e:
                        print(f"[boot] preload FAIL {p}: {e}", flush=True)
                    break

import json
import re
from dataclasses import dataclass

from PySide6.QtCore import (
    Qt, QAbstractNativeEventFilter, QObject, QPoint, QPointF, QPropertyAnimation,
    QRect, QSize, QUrl, QThread, QTimer, Signal, Slot,
)
from PySide6.QtGui import (
    QAction, QColor, QGuiApplication, QIcon, QPainter, QPixmap, QPolygonF,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

import yt_dlp


# ============================ Config persistente ============================

def _app_dir() -> Path:
    """Cartella dell'app. Quando compilato con PyInstaller, getattr(sys,
    'frozen', False) è True e dobbiamo usare la dir dell'eseguibile, non
    della cartella temporanea di _MEIPASS."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_DOWNLOAD_DIR = APP_DIR / "audio"

YT_URL_RE = re.compile(
    r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/\S+",
    re.IGNORECASE,
)


@dataclass
class Config:
    download_dir: Path = DEFAULT_DOWNLOAD_DIR

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                return cls(download_dir=Path(data.get("download_dir", str(DEFAULT_DOWNLOAD_DIR))))
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps({"download_dir": str(self.download_dir)}, indent=2),
            encoding="utf-8",
        )


# ============================ Icona generata ============================

def _draw_play_icon(size: int, fg: str, bg: str) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(bg))
    p.setPen(Qt.NoPen)
    inset = max(1, size // 32)
    radius = max(2, size // 5)
    p.drawRoundedRect(inset, inset, size - 2 * inset, size - 2 * inset, radius, radius)
    p.setBrush(QColor(fg))
    tri = QPolygonF([
        QPointF(size * 0.38, size * 0.28),
        QPointF(size * 0.74, size * 0.50),
        QPointF(size * 0.38, size * 0.72),
    ])
    p.drawPolygon(tri)
    p.end()
    return pix


def make_icon(fg: str = "#ff8a3d", bg: str = "#1a1410") -> QIcon:
    """Icona dell'app: carica icon.ico se presente, altrimenti la disegna."""
    ico_path = APP_DIR / "icon.ico"
    if ico_path.exists():
        return QIcon(str(ico_path))
    icon = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(_draw_play_icon(s, fg, bg))
    return icon


def _filled_play_icon(size: int = 18, fg: str = "#1a1410") -> QIcon:
    pix = QPixmap(size, size); pix.fill(Qt.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(fg)); p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(size * 0.30, size * 0.22),
        QPointF(size * 0.78, size * 0.50),
        QPointF(size * 0.30, size * 0.78),
    ]))
    p.end()
    return QIcon(pix)


def _filled_pause_icon(size: int = 18, fg: str = "#1a1410") -> QIcon:
    pix = QPixmap(size, size); pix.fill(Qt.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(fg)); p.setPen(Qt.NoPen)
    bar_w = size * 0.18
    gap = size * 0.12
    h = size * 0.56
    y = (size - h) / 2
    cx = size / 2
    p.drawRoundedRect(int(cx - gap / 2 - bar_w), int(y), int(bar_w), int(h), 2, 2)
    p.drawRoundedRect(int(cx + gap / 2), int(y), int(bar_w), int(h), 2, 2)
    p.end()
    return QIcon(pix)


def _volume_icon(size: int = 16, fg: str = "#ff8a3d", muted: bool = False) -> QIcon:
    pix = QPixmap(size, size); pix.fill(Qt.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen(); pen.setColor(QColor(fg)); pen.setWidthF(max(1.2, size / 12)); p.setPen(pen)
    p.setBrush(QColor(fg))
    # speaker body (triangolo + base)
    poly = QPolygonF([
        QPointF(size * 0.15, size * 0.40),
        QPointF(size * 0.35, size * 0.40),
        QPointF(size * 0.55, size * 0.22),
        QPointF(size * 0.55, size * 0.78),
        QPointF(size * 0.35, size * 0.60),
        QPointF(size * 0.15, size * 0.60),
    ])
    p.drawPolygon(poly)
    if not muted:
        p.setBrush(Qt.NoBrush)
        pen2 = p.pen(); pen2.setWidthF(max(1.0, size / 14)); p.setPen(pen2)
        p.drawArc(int(size * 0.55), int(size * 0.30), int(size * 0.25), int(size * 0.40), -60 * 16, 120 * 16)
    else:
        # X
        pen2 = p.pen(); pen2.setWidthF(max(1.2, size / 12)); p.setPen(pen2)
        p.drawLine(int(size * 0.65), int(size * 0.35), int(size * 0.85), int(size * 0.65))
        p.drawLine(int(size * 0.85), int(size * 0.35), int(size * 0.65), int(size * 0.65))
    p.end()
    return QIcon(pix)


def make_folder_icon(size: int = 18, fg: str = "#ff8a3d") -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor(fg))
    pen.setWidthF(max(1.2, size / 14))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # corpo cartella
    body = QRect(int(size * 0.12), int(size * 0.30), int(size * 0.76), int(size * 0.52))
    p.drawRoundedRect(body, 2, 2)
    # linguetta
    p.drawLine(int(size * 0.18), int(size * 0.30),
               int(size * 0.40), int(size * 0.30))
    p.drawLine(int(size * 0.18), int(size * 0.30),
               int(size * 0.22), int(size * 0.20))
    p.drawLine(int(size * 0.22), int(size * 0.20),
               int(size * 0.44), int(size * 0.20))
    p.drawLine(int(size * 0.44), int(size * 0.20),
               int(size * 0.48), int(size * 0.30))
    p.end()
    return QIcon(pix)


# ============================ Worker yt-dlp ============================

class DownloadSignals(QObject):
    progress = Signal(int, float, str)   # row_id, percent, status_text
    finished = Signal(int, str, bool, str)  # row_id, file_path, ok, error


class DownloadWorker(QThread):
    """
    Scarica un singolo URL. Format: bestaudio (Opus nativo se disponibile),
    nessuna riconversione → qualità originale di YouTube, file piccolo.
    """

    def __init__(self, row_id: int, url: str, out_dir: Path, signals: DownloadSignals):
        super().__init__()
        self.row_id = row_id
        self.url = url
        self.out_dir = out_dir
        self.signals = signals
        self._last_emit = 0.0

    def _hook(self, d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100.0) if total else 0.0
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            speed_kb = speed / 1024 if speed else 0
            txt = f"{pct:5.1f}%  •  {speed_kb:6.0f} KB/s  •  ETA {int(eta)}s"
            self.signals.progress.emit(self.row_id, pct, txt)
        elif status == "finished":
            self.signals.progress.emit(self.row_id, 100.0, "Finalizzazione…")

    def run(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        # bestaudio scarica direttamente lo stream audio nativo migliore.
        # YouTube serve Opus ~160 kbps in webm: zero riconversione, massima qualità.
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(self.out_dir / "%(title)s.%(ext)s"),
            "progress_hooks": [self._hook],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": False,
            "windowsfilenames": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                filename = ydl.prepare_filename(info)
            self.signals.finished.emit(self.row_id, filename, True, "")
        except Exception as e:
            self.signals.finished.emit(self.row_id, "", False, f"{type(e).__name__}: {e}")


# ============================ UI: riga singolo download ============================

class DownloadRow(QFrame):
    open_folder_requested = Signal(str)
    play_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, row_id: int, url: str = "", existing_file: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.row_id = row_id
        self.url = url
        self.file_path = existing_file
        self.is_library = bool(existing_file)
        self.setObjectName("DownloadRow")
        self.setStyleSheet("""
            #DownloadRow { background: #2b2018; border-radius: 8px; }
            QLabel { color: #fff4e8; }
            QLabel#status { color: #c9a98c; font-size: 11px; }
            QProgressBar { background: #1a1410; border: none; border-radius: 4px; height: 6px; text-align: center; color: transparent; }
            QProgressBar::chunk { background: #ff8a3d; border-radius: 4px; }
            QPushButton { background: transparent; color: #ff8a3d; border: 1px solid #6e4d34; border-radius: 4px; padding: 2px 8px; font-size: 11px; }
            QPushButton:hover { background: #5a3e2a; }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        initial_title = Path(existing_file).name if existing_file else self._short_url(url)
        self.title_lbl = QLabel(initial_title)
        self.title_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        self.title_lbl.setWordWrap(False)
        self.title_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title_lbl.setMinimumWidth(0)
        self.title_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._title_full = initial_title

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if self.is_library else 0)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.status_lbl = QLabel("Pronto" if self.is_library else "In coda…")
        self.status_lbl.setObjectName("status")
        if self.is_library:
            self.status_lbl.setStyleSheet("color: #c9a98c; font-size: 11px;")
        bottom.addWidget(self.status_lbl, 1)

        self.open_btn = QPushButton("Cartella")
        self.play_btn = QPushButton("Riproduci")
        self.del_btn = QPushButton("✕")
        self.del_btn.setToolTip("Elimina file")
        self.open_btn.clicked.connect(lambda: self.open_folder_requested.emit(self.file_path))
        self.play_btn.clicked.connect(lambda: self.play_requested.emit(self.file_path))
        self.del_btn.clicked.connect(lambda: self.delete_requested.emit(self.file_path))
        if self.is_library:
            self.open_btn.show()
            self.play_btn.show()
            self.del_btn.show()
            self.progress.hide()
        else:
            self.open_btn.hide()
            self.play_btn.hide()
            self.del_btn.hide()
        bottom.addWidget(self.open_btn)
        bottom.addWidget(self.play_btn)
        bottom.addWidget(self.del_btn)

        lay.addWidget(self.title_lbl)
        lay.addWidget(self.progress)
        lay.addLayout(bottom)

    @staticmethod
    def _short_url(url: str) -> str:
        m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
        return f"YouTube • {m.group(1)}" if m else url[:60]

    def _apply_elided_title(self) -> None:
        fm = self.title_lbl.fontMetrics()
        avail = max(40, self.title_lbl.width() - 6)
        self.title_lbl.setText(fm.elidedText(self._title_full, Qt.ElideMiddle, avail))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elided_title()

    @Slot(float, str)
    def on_progress(self, pct: float, status: str) -> None:
        self.progress.setValue(int(pct))
        self.status_lbl.setText(status)

    @Slot(str, bool, str)
    def on_finished(self, file_path: str, ok: bool, error: str) -> None:
        if ok:
            self.file_path = file_path
            self._title_full = Path(file_path).name
            self.title_lbl.setToolTip(self._title_full)
            self._apply_elided_title()
            self.progress.setValue(100)
            self.progress.hide()
            self.status_lbl.setText("Pronto")
            self.status_lbl.setStyleSheet("color: #6ee7b7; font-size: 11px;")
            self.is_library = True
            self.open_btn.show()
            self.play_btn.show()
            self.del_btn.show()
        else:
            self.status_lbl.setText(f"Errore: {error}")
            self.status_lbl.setStyleSheet("color: #fca5a5; font-size: 11px;")


# ============================ Player integrato ============================

def _fmt_time(ms: int) -> str:
    if ms <= 0:
        return "0:00"
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class PlayerWidget(QFrame):
    """Mini player audio integrato. Usa QMediaPlayer con backend FFmpeg."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Player")
        self.setStyleSheet("""
            #Player { background: #2a1f17; border-radius: 10px; border: 1px solid #5a3e2a; }
            QLabel { color: #fff4e8; }
            QLabel#track { font-weight: 600; font-size: 12px; }
            QLabel#time  { color: #c9a98c; font-size: 10px; }
            QPushButton#playbtn {
                background: #ff8a3d; border: none; border-radius: 16px;
                min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;
            }
            QPushButton#playbtn:hover { background: #ffa66b; }
            QPushButton#playbtn:disabled { background: #6e4d34; }
            QPushButton#flat {
                background: transparent; border: none; padding: 2px;
                min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px;
            }
            QSlider::groove:horizontal {
                height: 4px; background: #1a1410; border-radius: 2px;
            }
            QSlider::sub-page:horizontal { background: #ff8a3d; border-radius: 2px; }
            QSlider::add-page:horizontal { background: #1a1410; border-radius: 2px; }
            QSlider::handle:horizontal {
                background: #fff4e8; width: 10px; height: 10px;
                margin: -4px 0; border-radius: 5px;
            }
            QSlider::handle:horizontal:hover { background: #ffffff; }
        """)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(0.7)
        self._user_seeking = False
        self._title_full = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # Riga 1: titolo
        self.track_lbl = QLabel("Nessun brano in riproduzione")
        self.track_lbl.setObjectName("track")
        self.track_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.track_lbl.setMinimumWidth(0)
        lay.addWidget(self.track_lbl)

        # Riga 2: seek slider + tempo
        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
        self.pos_slider = QSlider(Qt.Horizontal)
        self.pos_slider.setRange(0, 0)
        self.pos_slider.sliderPressed.connect(self._on_seek_pressed)
        self.pos_slider.sliderReleased.connect(self._on_seek_released)
        self.pos_slider.sliderMoved.connect(self._on_seek_moved)
        self.time_lbl = QLabel("0:00 / 0:00")
        self.time_lbl.setObjectName("time")
        seek_row.addWidget(self.pos_slider, 1)
        seek_row.addWidget(self.time_lbl)
        lay.addLayout(seek_row)

        # Riga 3: controlli (play/pause + volume)
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        self.play_btn = QPushButton()
        self.play_btn.setObjectName("playbtn")
        self.play_btn.setIcon(_filled_play_icon(18))
        self.play_btn.setIconSize(QSize(18, 18))
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self.toggle_play)
        ctrl_row.addWidget(self.play_btn)

        ctrl_row.addStretch(1)

        self.vol_icon_btn = QPushButton()
        self.vol_icon_btn.setObjectName("flat")
        self.vol_icon_btn.setIcon(_volume_icon(16))
        self.vol_icon_btn.setIconSize(QSize(16, 16))
        self.vol_icon_btn.setCursor(Qt.PointingHandCursor)
        self.vol_icon_btn.clicked.connect(self._toggle_mute)
        ctrl_row.addWidget(self.vol_icon_btn)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.setFixedWidth(80)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        ctrl_row.addWidget(self.vol_slider)
        lay.addLayout(ctrl_row)

        # Segnali del player
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.errorOccurred.connect(self._on_error)

    # ---- API pubblica ----

    def load_and_play(self, file_path: str) -> None:
        if not file_path or not Path(file_path).exists():
            return
        self._title_full = Path(file_path).name
        self._apply_elided_title()
        self.track_lbl.setToolTip(self._title_full)
        self._player.setSource(QUrl.fromLocalFile(str(Path(file_path).resolve())))
        self.play_btn.setEnabled(True)
        self._player.play()

    def toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def stop(self) -> None:
        self._player.stop()

    # ---- internals ----

    def _apply_elided_title(self) -> None:
        fm = self.track_lbl.fontMetrics()
        avail = max(60, self.track_lbl.width() - 6)
        self.track_lbl.setText(fm.elidedText(self._title_full or "Nessun brano in riproduzione",
                                             Qt.ElideMiddle, avail))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elided_title()

    @Slot(int)
    def _on_position(self, pos: int) -> None:
        if not self._user_seeking:
            self.pos_slider.setValue(pos)
        self._update_time_label(pos, self._player.duration())

    @Slot(int)
    def _on_duration(self, dur: int) -> None:
        self.pos_slider.setRange(0, max(0, dur))
        self._update_time_label(self._player.position(), dur)

    def _update_time_label(self, pos: int, dur: int) -> None:
        self.time_lbl.setText(f"{_fmt_time(pos)} / {_fmt_time(dur)}")

    @Slot(QMediaPlayer.PlaybackState)
    def _on_state(self, state) -> None:
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setIcon(_filled_pause_icon(18))
        else:
            self.play_btn.setIcon(_filled_play_icon(18))

    @Slot(QMediaPlayer.Error, str)
    def _on_error(self, err, msg: str) -> None:
        if err == QMediaPlayer.NoError:
            return
        self.track_lbl.setText(f"Errore player: {msg or err}")
        self.track_lbl.setToolTip(msg or "")

    def _on_seek_pressed(self) -> None:
        self._user_seeking = True

    def _on_seek_released(self) -> None:
        self._player.setPosition(self.pos_slider.value())
        self._user_seeking = False

    def _on_seek_moved(self, value: int) -> None:
        self._update_time_label(value, self._player.duration())

    def _on_volume_changed(self, value: int) -> None:
        self._audio.setVolume(value / 100.0)
        self._audio.setMuted(False)
        self.vol_icon_btn.setIcon(_volume_icon(16, muted=(value == 0)))

    def _toggle_mute(self) -> None:
        self._audio.setMuted(not self._audio.isMuted())
        self.vol_icon_btn.setIcon(_volume_icon(16, muted=self._audio.isMuted()))


# ============================ Popup principale ============================

POPUP_W = 420
POPUP_H_MIN = 260
POPUP_MARGIN = 12

class PopupWindow(QWidget):
    closed = Signal()

    AUDIO_EXTS = {".webm", ".opus", ".m4a", ".mp3", ".aac", ".ogg", ".oga", ".wav", ".flac"}

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._next_row_id = 0
        self._workers: dict[int, DownloadWorker] = {}
        self._rows: dict[int, DownloadRow] = {}
        self._library_paths: set[str] = set()  # file_path → riga già presente

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(POPUP_W)

        # Card container per avere bordi arrotondati
        self.card = QFrame(self)
        self.card.setObjectName("Card")
        self.card.setStyleSheet("""
            #Card { background: #1a1410; border-radius: 14px; border: 1px solid #5a3e2a; }
            QLabel { color: #fff4e8; }
            QLabel#title { font-size: 14px; font-weight: 700; }
            QLabel#hint  { color: #c9a98c; font-size: 11px; }
            QLineEdit {
                background: #2b2018; color: #fff4e8; border: 1px solid #6e4d34;
                border-radius: 8px; padding: 8px 10px; font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #ff8a3d; }
            QPushButton#primary {
                background: #ff8a3d; color: #1a1410; border: none;
                border-radius: 8px; padding: 8px 14px; font-weight: 700;
            }
            QPushButton#primary:hover { background: #ffa66b; }
            QPushButton#primary:disabled { background: #6e4d34; color: #c9a98c; }
            QPushButton#secondary {
                background: transparent; color: #c9a98c; border: none; font-size: 11px;
            }
            QPushButton#secondary:hover { color: #fff4e8; }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; }
            QScrollBar::handle:vertical { background: #6e4d34; border-radius: 3px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)

        inner = QVBoxLayout(self.card)
        inner.setContentsMargins(16, 14, 16, 14)
        inner.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("Cove")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)
        self.folder_btn = QPushButton("  Cartella")
        self.folder_btn.setIcon(make_folder_icon(16))
        self.folder_btn.setIconSize(QSize(16, 16))
        self.folder_btn.setObjectName("secondary")
        self.folder_btn.setToolTip("Cambia cartella di destinazione")
        self.folder_btn.setCursor(Qt.PointingHandCursor)
        self.folder_btn.clicked.connect(self.choose_folder)
        header.addWidget(self.folder_btn)
        inner.addLayout(header)

        self.folder_lbl = QLabel(self._folder_label())
        self.folder_lbl.setObjectName("hint")
        self.folder_lbl.setToolTip(str(self.config.download_dir))
        inner.addWidget(self.folder_lbl)

        # URL row
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Incolla qui un link YouTube…")
        self.url_edit.returnPressed.connect(self.start_download)
        self.dl_btn = QPushButton("Scarica")
        self.dl_btn.setObjectName("primary")
        self.dl_btn.setCursor(Qt.PointingHandCursor)
        self.dl_btn.clicked.connect(self.start_download)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.dl_btn)
        inner.addLayout(url_row)

        # Lista download (scroll)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.list_container)
        self.scroll.setMinimumHeight(80)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner.addWidget(self.scroll, 1)

        # Player integrato
        self.player = PlayerWidget()
        inner.addWidget(self.player)

        # Animazione
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve_OutCubic())
        self._anim.finished.connect(self._on_anim_finished)
        self._closing = False

        # Popola la libreria all'avvio
        self._refresh_library()

    # ----- helpers -----

    def _folder_label(self) -> str:
        s = str(self.config.download_dir)
        return s if len(s) <= 44 else "…" + s[-42:]

    def _target_geometry(self) -> QRect:
        screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        # Altezza: base 360 (header + url + player) + 56 per riga (max 6 visibili,
        # le altre via scroll). Cap a 80% dell'altezza schermo.
        n_rows = sum(1 for r in self._rows.values())
        h = max(POPUP_H_MIN, 360 + 56 * min(n_rows, 6))
        h = min(h, int(avail.height() * 0.85))
        x = avail.right() - POPUP_W - POPUP_MARGIN + 1
        y = avail.bottom() - h - POPUP_MARGIN + 1
        return QRect(x, y, POPUP_W, h)

    def _offscreen_geometry(self, target: QRect) -> QRect:
        # parte fuori schermo in basso, slide-up
        screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
        return QRect(target.x(), screen.geometry().bottom() + 4, target.width(), target.height())

    # ----- show/hide animati -----

    def show_animated(self) -> None:
        self._closing = False
        self._refresh_library()
        target = self._target_geometry()
        start = self._offscreen_geometry(target)
        self.setGeometry(start)
        self.prefill_from_clipboard()
        self.show()
        self.raise_()
        self.activateWindow()
        self.url_edit.setFocus()
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target)
        self._anim.start()

    def hide_animated(self) -> None:
        if not self.isVisible():
            return
        self._closing = True
        target = self._offscreen_geometry(self.geometry())
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        if self._closing:
            self.hide()
            self._closing = False
            self.closed.emit()

    def toggle(self) -> None:
        if self.isVisible() and not self._closing:
            self.hide_animated()
        else:
            self.show_animated()

    # ----- clipboard prefill -----

    def prefill_from_clipboard(self) -> None:
        text = (QGuiApplication.clipboard().text() or "").strip()
        if YT_URL_RE.match(text):
            self.url_edit.setText(text)
            self.url_edit.selectAll()

    # ----- azioni -----

    def choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Cartella di destinazione", str(self.config.download_dir))
        if d:
            self.config.download_dir = Path(d)
            self.config.save()
            self.folder_lbl.setText(self._folder_label())
            self.folder_lbl.setToolTip(str(self.config.download_dir))

    def start_download(self) -> None:
        url = self.url_edit.text().strip()
        if not YT_URL_RE.match(url):
            self.url_edit.setStyleSheet("border: 1px solid #fca5a5;")
            QTimer.singleShot(800, lambda: self.url_edit.setStyleSheet(""))
            return
        row_id = self._next_row_id
        self._next_row_id += 1

        row = DownloadRow(row_id, url=url)
        self._rows[row_id] = row
        self.list_layout.insertWidget(0, row)

        signals = DownloadSignals()
        signals.progress.connect(self._on_progress)
        signals.finished.connect(self._on_finished)
        row.open_folder_requested.connect(self._open_folder)
        row.play_requested.connect(self._play_file)
        row.delete_requested.connect(self._delete_file)

        worker = DownloadWorker(row_id, url, self.config.download_dir, signals)
        worker._signals_holder = signals  # noqa: keep ref alive
        worker.start()
        self._workers[row_id] = worker

        self.url_edit.clear()
        # ridimensiona popup
        new_geom = self._target_geometry()
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(new_geom)
        self._anim.start()

    @Slot(int, float, str)
    def _on_progress(self, row_id: int, pct: float, status: str) -> None:
        row = self._rows.get(row_id)
        if row:
            row.on_progress(pct, status)

    @Slot(int, str, bool, str)
    def _on_finished(self, row_id: int, file_path: str, ok: bool, error: str) -> None:
        row = self._rows.get(row_id)
        if row:
            row.on_finished(file_path, ok, error)
        # cleanup thread
        w = self._workers.pop(row_id, None)
        if w:
            w.quit()
        if ok and file_path:
            self._library_paths.add(str(Path(file_path).resolve()))
        # segnale all'app principale per la notifica di sistema
        self._notify(file_path if ok else "", ok, error)

    def _notify(self, file_path: str, ok: bool, error: str) -> None:
        app = QApplication.instance()
        tray = getattr(app, "tray_ref", None)
        if not tray:
            return
        if ok:
            tray.showMessage(
                "Download completato",
                Path(file_path).name,
                QSystemTrayIcon.Information,
                4000,
            )
        else:
            tray.showMessage("Download fallito", error, QSystemTrayIcon.Warning, 5000)

    @Slot(str)
    def _open_folder(self, file_path: str) -> None:
        if not file_path:
            return
        # apre Esplora risorse selezionando il file
        import subprocess
        subprocess.Popen(["explorer", "/select,", str(Path(file_path))])

    @Slot(str)
    def _play_file(self, file_path: str) -> None:
        if not file_path:
            return
        self.player.load_and_play(file_path)

    @Slot(str)
    def _delete_file(self, file_path: str) -> None:
        if not file_path:
            return
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError:
            return
        key = str(Path(file_path).resolve())
        self._library_paths.discard(key)
        # rimuovi anche la riga
        for rid, row in list(self._rows.items()):
            if str(Path(row.file_path).resolve()) == key if row.file_path else False:
                row.setParent(None)
                row.deleteLater()
                self._rows.pop(rid, None)
                break

    def _refresh_library(self) -> None:
        """Scansiona la cartella di download e aggiunge righe per i file
        non ancora presenti nella lista."""
        d = self.config.download_dir
        if not d.exists():
            return
        try:
            files = [p for p in d.iterdir()
                     if p.is_file() and p.suffix.lower() in self.AUDIO_EXTS]
        except OSError:
            return
        # ordina per data di modifica decrescente (più recenti in alto)
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files:
            key = str(p.resolve())
            if key in self._library_paths:
                continue
            self._library_paths.add(key)
            row_id = self._next_row_id
            self._next_row_id += 1
            row = DownloadRow(row_id, existing_file=str(p))
            row.open_folder_requested.connect(self._open_folder)
            row.play_requested.connect(self._play_file)
            row.delete_requested.connect(self._delete_file)
            self._rows[row_id] = row
            # inserisci prima dello stretch finale ma dopo i download attivi
            insert_at = self._first_library_index()
            self.list_layout.insertWidget(insert_at, row)

    def _first_library_index(self) -> int:
        """Indice di inserimento per le righe libreria: dopo tutti i download
        attivi (che stanno in cima) e prima dello stretch."""
        idx = 0
        for i in range(self.list_layout.count()):
            item = self.list_layout.itemAt(i)
            w = item.widget()
            if isinstance(w, DownloadRow) and not w.is_library:
                idx = i + 1
        return idx

    # nascondi se clicco fuori
    def focusOutEvent(self, event) -> None:
        # disattivato: rende fastidioso il drag della finestra; chiudi via tray o ESC
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide_animated()
        else:
            super().keyPressEvent(event)


# QEasingCurve helper (PySide6 expone l'enum su QEasingCurve.OutCubic)
def QEasingCurve_OutCubic():
    from PySide6.QtCore import QEasingCurve
    c = QEasingCurve()
    c.setType(QEasingCurve.OutCubic)
    return c


# ============================ Hotkey multimediali globali ============================

# Permette di controllare l'app coi tasti Play/Pause delle cuffie e tastiere
# multimediali. Su Windows usiamo RegisterHotKey + WM_HOTKEY intercettato
# dal native event filter di Qt.

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _user32.RegisterHotKey.restype = wintypes.BOOL
    _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.UnregisterHotKey.restype = wintypes.BOOL

    WM_HOTKEY = 0x0312
    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_MEDIA_STOP       = 0xB2
    VK_MEDIA_PLAY_PAUSE = 0xB3

    class MediaKeyFilter(QAbstractNativeEventFilter):
        def __init__(self):
            super().__init__()
            self.mapping: dict[int, callable] = {}

        def nativeEventFilter(self, eventType, message):
            if eventType in ("windows_generic_MSG", b"windows_generic_MSG"):
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    cb = self.mapping.get(int(msg.wParam))
                    if cb:
                        cb()
                        return True, 0
            return False, 0

    def register_media_hotkeys(callbacks: dict) -> MediaKeyFilter | None:
        """callbacks: { VK_MEDIA_*: callable }. Restituisce il filtro,
        oppure None se nessun hotkey è stato registrato."""
        filt = MediaKeyFilter()
        registered = 0
        for vk, fn in callbacks.items():
            if _user32.RegisterHotKey(None, vk, 0, vk):
                filt.mapping[vk] = fn
                registered += 1
        return filt if registered else None

    def unregister_media_hotkeys(filt: "MediaKeyFilter") -> None:
        for vk in list(filt.mapping):
            _user32.UnregisterHotKey(None, vk)
        filt.mapping.clear()
else:
    def register_media_hotkeys(callbacks):  # type: ignore[no-redef]
        return None
    def unregister_media_hotkeys(filt):  # type: ignore[no-redef]
        pass
    VK_MEDIA_PLAY_PAUSE = VK_MEDIA_STOP = VK_MEDIA_NEXT_TRACK = VK_MEDIA_PREV_TRACK = 0  # type: ignore


# ============================ Main ============================

def main() -> int:
    QApplication.setQuitOnLastWindowClosed(False)
    app = QApplication(sys.argv)
    app.setApplicationName("Cove")
    app.setOrganizationName("Cove")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray non disponibile su questo sistema.", file=sys.stderr)
        return 1

    config = Config.load()
    icon = make_icon()
    app.setWindowIcon(icon)

    popup = PopupWindow(config)

    tray = QSystemTrayIcon(icon)
    tray.setToolTip("Cove — click per aprire")
    app.tray_ref = tray  # type: ignore[attr-defined]

    menu = QMenu()
    act_open = QAction("Apri pannello", menu)
    act_open.triggered.connect(popup.show_animated)
    menu.addAction(act_open)

    act_folder = QAction("Apri cartella download", menu)
    def open_dl_folder():
        import subprocess
        config.download_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(config.download_dir)])
    act_folder.triggered.connect(open_dl_folder)
    menu.addAction(act_folder)

    menu.addSeparator()
    act_quit = QAction("Esci", menu)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_quit)
    tray.setContextMenu(menu)

    def on_activated(reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            popup.toggle()
    tray.activated.connect(on_activated)

    # Hotkey multimediali globali (Play/Pause delle cuffie, tastiere multimediali)
    player = popup.player

    def _next_track():
        # Niente coda al momento: avanti = +10s
        p = player._player.position()
        d = player._player.duration()
        if d > 0:
            player._player.setPosition(min(p + 10000, d))

    def _prev_track():
        p = player._player.position()
        player._player.setPosition(max(0, p - 10000))

    media_filter = register_media_hotkeys({
        VK_MEDIA_PLAY_PAUSE: player.toggle_play,
        VK_MEDIA_STOP: player.stop,
        VK_MEDIA_NEXT_TRACK: _next_track,
        VK_MEDIA_PREV_TRACK: _prev_track,
    })
    if media_filter:
        app.installNativeEventFilter(media_filter)
        app.aboutToQuit.connect(lambda: unregister_media_hotkeys(media_filter))
        app.media_filter_ref = media_filter  # tieni la referenza viva

    tray.show()
    tray.showMessage(
        "Cove attivo",
        "Tasti Play/Pausa delle cuffie attivi. Click sull'icona per il pannello.",
        QSystemTrayIcon.Information,
        2500,
    )

    def excepthook(exctype, value, tb):
        traceback.print_exception(exctype, value, tb)
        tray.showMessage("Errore", f"{exctype.__name__}: {value}", QSystemTrayIcon.Critical, 5000)
    sys.excepthook = excepthook

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
