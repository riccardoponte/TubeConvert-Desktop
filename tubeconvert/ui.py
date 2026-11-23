"""Interfaccia grafica (porting di MainActivity + ConverterScreen, LibraryScreen,
SettingsScreen e dei componenti Compose)."""
from __future__ import annotations

import datetime
import os
import subprocess
import sys

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
                               QSizePolicy, QSlider, QStackedWidget, QTabWidget, QVBoxLayout,
                               QWidget)

from .models import (AudioQuality, ConversionTask, DownloadedItem, MediaFormat, TaskStatus,
                     VideoQuality)
from .storage import default_audio_dir, default_video_dir
from .viewmodel import TubeConvertViewModel

APP_VERSION = "TubeConvert v1.1"

try:  # QtWebEngine è opzionale (non incluso nel runtime portatile)
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except Exception:  # noqa: BLE001
    HAS_WEBENGINE = False

# ----------------------------------------------------------------- tema
PRIMARY = "#FF3D57"
PRIMARY_DARK = "#C81E3A"
BG = "#0F0F14"
SURFACE = "#1A1A22"
SURFACE_VAR = "#262631"
OUTLINE = "#3A3A48"
ON_SURFACE = "#F2F2F7"
ON_SURFACE_VAR = "#A6A6B5"
TERTIARY = "#4CC38A"
ERROR = "#FF6B6B"

STYLE = f"""
* {{ font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 10pt; color: {ON_SURFACE}; }}
QMainWindow, QWidget#root, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; }}
QFrame#card {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 16px; }}
QFrame#nav {{ background: {SURFACE}; border-top: 1px solid {OUTLINE}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 20pt; font-weight: 700; }}
QLabel#subtitle {{ color: {ON_SURFACE_VAR}; }}
QLabel#section {{ font-size: 12pt; font-weight: 600; }}
QLabel#muted {{ color: {ON_SURFACE_VAR}; font-size: 9pt; }}
QLabel#error {{ color: {ERROR}; font-size: 9pt; }}
QLabel#ok {{ color: {TERTIARY}; font-size: 9pt; font-weight: 600; }}
QLabel#chip {{ background: {SURFACE_VAR}; border-radius: 8px; padding: 2px 8px; font-size: 8.5pt; color: {ON_SURFACE_VAR}; }}
QPlainTextEdit, QLineEdit {{ background: {SURFACE_VAR}; border: 1px solid {OUTLINE}; border-radius: 12px; padding: 8px; selection-background-color: {PRIMARY}; }}
QPlainTextEdit:focus, QLineEdit:focus {{ border: 1px solid {PRIMARY}; }}
QPushButton {{ background: {SURFACE_VAR}; border: 1px solid {OUTLINE}; border-radius: 10px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {PRIMARY}; }}
QPushButton:disabled {{ color: #666; border-color: #2c2c36; }}
QPushButton#primary {{ background: {PRIMARY}; border: none; font-weight: 700; padding: 12px 18px; font-size: 11pt; }}
QPushButton#primary:hover {{ background: {PRIMARY_DARK}; }}
QPushButton#primary:disabled {{ background: #55303a; color: #aaa; }}
QPushButton#danger {{ color: {ERROR}; }}
QPushButton#text {{ background: transparent; border: none; color: {PRIMARY}; font-weight: 600; padding: 4px 8px; }}
QPushButton#chipBtn {{ background: {SURFACE_VAR}; border: 1px solid {OUTLINE}; border-radius: 12px; padding: 10px 12px; text-align: left; }}
QPushButton#chipBtn:checked {{ background: #3a1820; border: 2px solid {PRIMARY}; }}
QPushButton#filter {{ border-radius: 14px; padding: 5px 14px; }}
QPushButton#filter:checked {{ background: {PRIMARY}; border-color: {PRIMARY}; font-weight: 600; }}
QPushButton#navBtn {{ background: transparent; border: none; border-radius: 14px; padding: 8px 20px; color: {ON_SURFACE_VAR}; font-weight: 600; }}
QPushButton#navBtn:checked {{ background: #3a1820; color: {PRIMARY}; }}
QProgressBar {{ background: {SURFACE_VAR}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 4px; }}
QSlider::groove:horizontal {{ background: {SURFACE_VAR}; height: 4px; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {PRIMARY}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ON_SURFACE}; width: 12px; margin: -5px 0; border-radius: 6px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {OUTLINE}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: {SURFACE_VAR}; padding: 8px 16px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {PRIMARY}; }}
QDialog, QMessageBox {{ background: {SURFACE}; }}
QToolTip {{ background: {SURFACE_VAR}; color: {ON_SURFACE}; border: 1px solid {OUTLINE}; }}
"""


# ----------------------------------------------------------------- utilità
def human_size(n: int) -> str:
    if n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.1f} {units[i]}"


def fmt_ms(ms: int) -> str:
    s = max(ms, 0) // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def fmt_date(ts_ms: int) -> str:
    mesi = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
    d = datetime.datetime.fromtimestamp(ts_ms / 1000)
    return f"{d.day:02d} {mesi[d.month - 1]} {d.year}, {d:%H:%M}"


def open_external(path: str) -> bool:
    if not os.path.exists(path):
        return False
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return True


def reveal_in_folder(path: str):
    if os.name == "nt" and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


def clear_layout(layout):
    while layout.count():
        it = layout.takeAt(0)
        w = it.widget()
        if w is not None:
            w.deleteLater()
        elif it.layout() is not None:
            clear_layout(it.layout())


def label(text: str, obj: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


def card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    return f, lay


def button(text: str, obj: str | None = None, cb=None, tip: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if obj:
        b.setObjectName(obj)
    if obj == "chipBtn":
        b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        b.setMinimumWidth(60)
    b.setCursor(Qt.PointingHandCursor)
    if cb:
        b.clicked.connect(cb)
    if tip:
        b.setToolTip(tip)
    return b


# ----------------------------------------------------------------- miniature
class ThumbnailLoader:
    def __init__(self):
        self.nam = QNetworkAccessManager()
        self.cache: dict[str, QPixmap] = {}
        self.waiting: dict[str, list] = {}

    def load(self, url: str, target: QLabel, size: QSize):
        def apply(pm: QPixmap):
            try:
                target.setPixmap(rounded(pm.scaled(size, Qt.KeepAspectRatioByExpanding,
                                                   Qt.SmoothTransformation), size, 10))
            except RuntimeError:
                pass  # widget già distrutto

        if url in self.cache:
            apply(self.cache[url])
            return
        if url in self.waiting:
            self.waiting[url].append(apply)
            return
        self.waiting[url] = [apply]
        reply = self.nam.get(QNetworkRequest(QUrl(url)))

        def done():
            pm = QPixmap()
            pm.loadFromData(reply.readAll())
            reply.deleteLater()
            cbs = self.waiting.pop(url, [])
            if not pm.isNull():
                self.cache[url] = pm
                for c in cbs:
                    c(pm)

        reply.finished.connect(done)


def rounded(pm: QPixmap, size: QSize, radius: int) -> QPixmap:
    out = QPixmap(size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size.width(), size.height(), radius, radius)
    p.setClipPath(path)
    x = (pm.width() - size.width()) // 2
    y = (pm.height() - size.height()) // 2
    p.drawPixmap(-x, -y, pm)
    p.end()
    return out


THUMBS: ThumbnailLoader | None = None


def thumb_label(url: str, w: int = 128, h: int = 72) -> QLabel:
    lb = QLabel()
    lb.setFixedSize(w, h)
    lb.setStyleSheet(f"background:{SURFACE_VAR}; border-radius:10px;")
    lb.setAlignment(Qt.AlignCenter)
    lb.setToolTip("Thumbnail video")
    if url and THUMBS:
        THUMBS.load(url, lb, QSize(w, h))
    return lb


# ================================================================ player audio
class AudioPlayerManager:
    """Porting di player/AudioPlayerManager.kt."""

    def __init__(self):
        self.player = QMediaPlayer()
        self.output = QAudioOutput()
        self.output.setVolume(1.0)
        self.player.setAudioOutput(self.output)
        self.track_title = ""
        self.track_author = ""
        self.thumbnail_url = ""
        self.file_path = ""

    def play_track(self, item: DownloadedItem):
        self.track_title, self.track_author = item.title, item.author
        self.thumbnail_url, self.file_path = item.thumbnail_url, item.file_path
        self.player.setSource(QUrl.fromLocalFile(item.file_path))
        self.player.play()

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop(self):
        self.player.stop()
        self.player.setSource(QUrl())


class MiniAudioPlayer(QFrame):
    def __init__(self, mgr: AudioPlayerManager):
        super().__init__()
        self.mgr = mgr
        self.setObjectName("card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.thumb_box = QHBoxLayout()
        lay.addLayout(self.thumb_box)
        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        self.state = label("In riproduzione", "ok")
        top.addWidget(self.state)
        top.addStretch()
        col.addLayout(top)
        self.title = label("", "section")
        self.author = label("", "muted")
        col.addWidget(self.title)
        col.addWidget(self.author)
        row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.mgr.player.setPosition(v))
        self.time = label("00:00 / 00:00", "muted")
        row.addWidget(self.slider, 1)
        row.addWidget(self.time)
        col.addLayout(row)
        lay.addLayout(col, 1)
        self.play_btn = button("⏸", cb=self.mgr.toggle, tip="Riproduci / Pausa")
        self.play_btn.setFixedWidth(46)
        lay.addWidget(self.play_btn)
        lay.addWidget(button("✕", cb=self.close_player, tip="Chiudi player"))
        p = mgr.player
        p.positionChanged.connect(self._pos)
        p.durationChanged.connect(lambda d: self.slider.setRange(0, d))
        p.playbackStateChanged.connect(self._state)
        self.hide()

    def show_track(self):
        clear_layout(self.thumb_box)
        self.thumb_box.addWidget(thumb_label(self.mgr.thumbnail_url, 64, 64))
        self.title.setText(self.mgr.track_title)
        self.author.setText(self.mgr.track_author)
        self.show()

    def _pos(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self.time.setText(f"{fmt_ms(pos)} / {fmt_ms(self.mgr.player.duration())}")

    def _state(self, st):
        playing = st == QMediaPlayer.PlayingState
        self.play_btn.setText("⏸" if playing else "▶")
        self.state.setText("In riproduzione" if playing else "In pausa")

    def close_player(self):
        self.mgr.stop()
        self.hide()


# ================================================================ dialog video
EMBED_HTML = """<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>* {{ box-sizing: border-box; }} html, body {{ margin:0; padding:0; width:100%; height:100%; background:#000; overflow:hidden; }}
iframe {{ width:100%; height:100%; border:none; display:block; }}</style></head>
<body><iframe src="https://www.youtube.com/embed/{vid}?autoplay=1&enablejsapi=1&playsinline=1&rel=0&modestbranding=1"
allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></body></html>"""


class VideoPlayerDialog(QDialog):
    """Porting di VideoPlayerDialog.kt: scheda file scaricato + scheda video originale."""

    def __init__(self, parent, title: str, video_id: str, file_path: str | None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(960, 620)
        self.file_path = file_path
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(label(title, "section", wrap=True), 1)
        lay.addLayout(head)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.player = None
        if file_path and os.path.exists(file_path):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            vw = QVideoWidget()
            v.addWidget(vw, 1)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(vw)
            self.player.setSource(QUrl.fromLocalFile(file_path))
            ctr = QHBoxLayout()
            pb = button("⏸", cb=self._toggle)
            pb.setFixedWidth(46)
            self.pb = pb
            sl = QSlider(Qt.Horizontal)
            tl = label("00:00 / 00:00", "muted")
            self.player.durationChanged.connect(lambda d: sl.setRange(0, d))

            def pos(p):
                if not sl.isSliderDown():
                    sl.setValue(p)
                tl.setText(f"{fmt_ms(p)} / {fmt_ms(self.player.duration())}")
            self.player.positionChanged.connect(pos)
            self.player.playbackStateChanged.connect(
                lambda s: pb.setText("⏸" if s == QMediaPlayer.PlayingState else "▶"))
            sl.sliderMoved.connect(self.player.setPosition)
            ctr.addWidget(pb)
            ctr.addWidget(sl, 1)
            ctr.addWidget(tl)
            v.addLayout(ctr)
            self.tabs.addTab(w, "File Scaricato")
            self.player.play()
        self.web = None
        if video_id and HAS_WEBENGINE:
            try:
                self.web = QWebEngineView()
                self.web.settings().setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
                self.web.setHtml(EMBED_HTML.format(vid=video_id), QUrl("https://www.youtube.com"))
                self.tabs.addTab(self.web, "Video Originale HD")
            except Exception:
                pass
        self.tabs.currentChanged.connect(self._tab_changed)
        foot = QHBoxLayout()
        if file_path:
            foot.addWidget(button("Apri con altra app", cb=self._open_external))
        if video_id:
            foot.addWidget(button("Apri su YouTube", cb=lambda: QDesktopServices.openUrl(
                QUrl("https://www.youtube.com/watch?v=" + video_id))))
        foot.addStretch()
        foot.addWidget(button("Chiudi player", "primary", cb=self.close))
        lay.addLayout(foot)

    def _toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _tab_changed(self, i):
        if self.player and self.tabs.widget(i) is self.web:
            self.player.pause()

    def _open_external(self):
        if self.player:
            self.player.pause()
        if not open_external(self.file_path):
            QMessageBox.warning(self, "TubeConvert", "File non trovato sul dispositivo")

    def closeEvent(self, e):
        if self.player:
            self.player.stop()
        if self.web:
            self.web.setHtml("")
        super().closeEvent(e)


# ================================================================ componenti
class VideoPreviewCard(QFrame):
    def __init__(self, info, on_remove, on_preview):
        super().__init__()
        self.setObjectName("card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(thumb_label(info.thumbnail_url))
        col = QVBoxLayout()
        t = label(info.title, wrap=True)
        t.setStyleSheet("font-weight:600;")
        col.addWidget(t)
        col.addWidget(label(info.author, "muted"))
        col.addStretch()
        lay.addLayout(col, 1)
        lay.addWidget(button("▶", cb=on_preview, tip="Anteprima video"))
        lay.addWidget(button("✕", "danger", cb=on_remove, tip="Rimuovi video"))


class ConversionTaskCard(QFrame):
    def __init__(self, vm: TubeConvertViewModel, task: ConversionTask, on_play):
        super().__init__()
        self.vm, self.task, self.on_play = vm, task, on_play
        self.setObjectName("card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(thumb_label(task.thumbnail_url))
        col = QVBoxLayout()
        col.setSpacing(4)
        t = label(task.title, wrap=True)
        t.setStyleSheet("font-weight:600;")
        col.addWidget(t)
        info = QHBoxLayout()
        ext = "M4A" if task.format is MediaFormat.MP3 else "MP4"
        info.addWidget(label(f"{ext} • {task.quality_label}", "chip"))
        self.status = label("", "muted")
        info.addWidget(self.status)
        info.addStretch()
        col.addLayout(info)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        col.addWidget(self.bar)
        self.detail = label("", "muted", wrap=True)
        col.addWidget(self.detail)
        lay.addLayout(col, 1)
        self.btns = QVBoxLayout()
        lay.addLayout(self.btns)
        self._last_status = None
        self.refresh()

    def refresh(self):
        t = self.task
        self.bar.setValue(int(t.progress * 1000))
        if t.status is TaskStatus.COMPLETED:
            self.status.setObjectName("ok")
            self.status.setText("✓ Completato")
            self.detail.setObjectName("muted")
            self.detail.setText(f"{human_size(t.total_bytes)} • {os.path.basename(t.output_file_path)}")
            self.detail.setToolTip(t.output_file_path)
        elif t.status is TaskStatus.FAILED:
            self.status.setObjectName("error")
            self.status.setText("Fallito")
            self.detail.setObjectName("error")
            self.detail.setText(t.error_message or "Download non riuscito. Riprova.")
        else:
            self.status.setObjectName("muted")
            pct = f"{int(t.progress * 100)}%"
            self.status.setText(f"{t.status_text or t.status.value} {pct}")
            self.detail.setObjectName("muted")
            self.detail.setText(t.speed_text)
        for w in (self.status, self.detail):
            w.style().unpolish(w)
            w.style().polish(w)
        if t.status != self._last_status:
            self._last_status = t.status
            clear_layout(self.btns)
            if t.is_active:
                self.btns.addWidget(button("Annulla", "danger", cb=lambda: self.vm.cancel(t.id)))
            elif t.status is TaskStatus.COMPLETED:
                self.btns.addWidget(button("▶ Riproduci", cb=lambda: self.on_play(t)))
                self.btns.addWidget(button("Mostra file", cb=lambda: reveal_in_folder(t.output_file_path)))
                self.btns.addWidget(button("Rimuovi", cb=lambda: self.vm.remove_task(t.id)))
            else:
                self.btns.addWidget(button("Riprova", cb=lambda: self.vm.retry(t.id)))
                self.btns.addWidget(button("Rimuovi", cb=lambda: self.vm.remove_task(t.id)))
            self.btns.addStretch()


class DownloadedItemCard(QFrame):
    def __init__(self, item: DownloadedItem, on_play, on_open, on_reveal, on_delete):
        super().__init__()
        self.setObjectName("card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(thumb_label(item.thumbnail_url, 112, 64))
        col = QVBoxLayout()
        col.setSpacing(3)
        t = label(item.title, wrap=True)
        t.setStyleSheet("font-weight:600;")
        col.addWidget(t)
        col.addWidget(label(item.author, "muted"))
        ext = "M4A" if item.is_audio else "MP4"
        exists = os.path.exists(item.file_path)
        meta = f"{ext} • {item.quality_label} • {human_size(item.file_size)} • {fmt_date(item.downloaded_timestamp)}"
        col.addWidget(label(meta, "muted"))
        if not exists:
            col.addWidget(label("File non trovato sul dispositivo", "error"))
        lay.addLayout(col, 1)
        b = QHBoxLayout()
        play = button("▶", cb=on_play, tip="Riproduci")
        play.setEnabled(exists)
        b.addWidget(play)
        ext_b = button("↗", cb=on_open, tip="Apri esterno")
        ext_b.setEnabled(exists)
        b.addWidget(ext_b)
        fold = button("📁", cb=on_reveal, tip="Mostra nella cartella")
        fold.setEnabled(exists)
        b.addWidget(fold)
        b.addWidget(button("🗑", "danger", cb=on_delete, tip="Elimina"))
        lay.addLayout(b)


def scroll_page() -> tuple[QScrollArea, QVBoxLayout]:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(24, 20, 24, 20)
    lay.setSpacing(14)
    sa.setWidget(inner)
    return sa, lay


def header(title: str, subtitle: str) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 4)
    v.setSpacing(2)
    v.addWidget(label(title, "title"))
    v.addWidget(label(subtitle, "subtitle"))
    return w


# ================================================================ schermate
class ConverterScreen(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win, self.vm = win, win.vm
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa, lay = scroll_page()
        outer.addWidget(sa)
        lay.addWidget(header("TubeConvert", "Converti & scarica YouTube in M4A / MP4"))

        # input
        c, cl = card()
        cl.addWidget(label("Incolla uno o più link YouTube…", "section"))
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("es. https://youtu.be/xxxx\n(un link per riga o separati da spazi)")
        self.input.setFixedHeight(96)
        self.input.textChanged.connect(lambda: self.vm.set_input_text(self.input.toPlainText()))
        cl.addWidget(self.input)
        r = QHBoxLayout()
        self.analyzing = label("Recupero informazioni video…", "muted")
        self.analyzing.hide()
        r.addWidget(self.analyzing)
        r.addStretch()
        r.addWidget(button("Incolla", cb=self._paste))
        r.addWidget(button("Pulisci", cb=lambda: self.input.setPlainText("")))
        self.analyze_btn = button("Analizza", cb=self.vm.analyze_links)
        r.addWidget(self.analyze_btn)
        cl.addLayout(r)
        lay.addWidget(c)

        # anteprime
        self.preview_title = label("", "section")
        lay.addWidget(self.preview_title)
        self.preview_box = QVBoxLayout()
        self.preview_box.setSpacing(8)
        lay.addLayout(self.preview_box)

        # formato
        c, cl = card()
        cl.addWidget(label("Formato di Conversione", "section"))
        fr = QHBoxLayout()
        self.fmt_group = QButtonGroup(self)
        self.fmt_btns = {}
        for f, desc in ((MediaFormat.MP3, "AAC • compatibile con ogni player"),
                        (MediaFormat.MP4, "H.264 + AAC • audio e video uniti")):
            b = button(f"{'🎵' if f is MediaFormat.MP3 else '🎬'}  {f.label}\n{desc}", "chipBtn",
                       cb=lambda _=False, f=f: self.vm.select_format(f))
            b.setCheckable(True)
            self.fmt_group.addButton(b)
            self.fmt_btns[f] = b
            fr.addWidget(b)
        cl.addLayout(fr)

        self.aq_title = label("Qualità Audio", "section")
        cl.addWidget(self.aq_title)
        self.aq_row = QWidget()
        ar = QHBoxLayout(self.aq_row)
        ar.setContentsMargins(0, 0, 0, 0)
        self.aq_group = QButtonGroup(self)
        self.aq_btns = {}
        for q in AudioQuality:
            b = button(f"{q.label}\n{q.description}", "chipBtn",
                       cb=lambda _=False, q=q: self.vm.select_audio_quality(q))
            b.setCheckable(True)
            self.aq_group.addButton(b)
            self.aq_btns[q] = b
            ar.addWidget(b)
        cl.addWidget(self.aq_row)

        self.vq_title = label("Risoluzione Video", "section")
        cl.addWidget(self.vq_title)
        self.vq_row = QWidget()
        vr = QHBoxLayout(self.vq_row)
        vr.setContentsMargins(0, 0, 0, 0)
        self.vq_group = QButtonGroup(self)
        self.vq_btns = {}
        for q in VideoQuality:
            b = button(f"{q.label}\n{q.description}", "chipBtn",
                       cb=lambda _=False, q=q: self.vm.select_video_quality(q))
            b.setCheckable(True)
            self.vq_group.addButton(b)
            self.vq_btns[q] = b
            vr.addWidget(b)
        cl.addWidget(self.vq_row)
        lay.addWidget(c)

        self.convert_btn = button("Converti e Scarica", "primary", cb=self.vm.start_conversion)
        lay.addWidget(self.convert_btn)

        # attività
        tr = QHBoxLayout()
        self.tasks_title = label("", "section")
        tr.addWidget(self.tasks_title)
        tr.addStretch()
        self.clear_btn = button("Pulisci completati", "text", cb=self.vm.clear_completed_tasks)
        tr.addWidget(self.clear_btn)
        lay.addLayout(tr)
        self.tasks_box = QVBoxLayout()
        self.tasks_box.setSpacing(8)
        lay.addLayout(self.tasks_box)
        lay.addStretch()
        self.task_cards: dict[str, ConversionTaskCard] = {}

        self.vm.parsed_changed.connect(self.refresh_parsed)
        self.vm.analyzing_changed.connect(self.analyzing.setVisible)
        self.vm.selection_changed.connect(self.refresh_selection)
        self.vm.tasks_changed.connect(self.refresh_tasks)
        self.vm.task_updated.connect(self.update_task)
        self.refresh_parsed()
        self.refresh_selection()
        self.refresh_tasks()

    def _paste(self):
        txt = QApplication.clipboard().text()
        if txt:
            cur = self.input.toPlainText().strip()
            self.input.setPlainText((cur + "\n" + txt).strip() if cur else txt)

    def refresh_parsed(self):
        if self.vm.input_text == "" and self.input.toPlainText() != "":
            self.input.blockSignals(True)
            self.input.setPlainText("")
            self.input.blockSignals(False)
        clear_layout(self.preview_box)
        n = len(self.vm.parsed_videos)
        self.preview_title.setText(f"Video pronti per la conversione ({n})")
        self.preview_title.setVisible(n > 0)
        for p in self.vm.parsed_videos:
            self.preview_box.addWidget(VideoPreviewCard(
                p, on_remove=lambda _=False, v=p.video_id: self.vm.remove_parsed_video(v),
                on_preview=lambda _=False, p=p: self.win.open_video_dialog(p.title, p.video_id, None)))
        self.refresh_selection()

    def refresh_selection(self):
        f = self.vm.selected_format
        self.fmt_btns[f].setChecked(True)
        self.aq_btns[self.vm.selected_audio_quality].setChecked(True)
        self.vq_btns[self.vm.selected_video_quality].setChecked(True)
        audio = f is MediaFormat.MP3
        self.aq_title.setVisible(audio)
        self.aq_row.setVisible(audio)
        self.vq_title.setVisible(not audio)
        self.vq_row.setVisible(not audio)
        n = len(self.vm.parsed_videos)
        ext = "M4A" if audio else "MP4"
        self.convert_btn.setText(f"Converti e Scarica ({n})  •  {ext}" if n > 1
                                 else f"Converti e Scarica in {ext}")

    def refresh_tasks(self):
        clear_layout(self.tasks_box)
        self.task_cards.clear()
        n = len(self.vm.tasks)
        self.tasks_title.setText(f"Download e Conversioni in corso ({n})")
        self.tasks_title.setVisible(n > 0)
        self.clear_btn.setVisible(any(not t.is_active for t in self.vm.tasks))
        for t in self.vm.tasks:
            c = ConversionTaskCard(self.vm, t, self.win.play_task)
            self.task_cards[t.id] = c
            self.tasks_box.addWidget(c)

    def update_task(self, task_id: str):
        c = self.task_cards.get(task_id)
        if c:
            c.refresh()
        self.clear_btn.setVisible(any(not t.is_active for t in self.vm.tasks))


class LibraryScreen(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win, self.vm = win, win.vm
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa, lay = scroll_page()
        outer.addWidget(sa)
        hr = QHBoxLayout()
        hr.addWidget(header("I Miei Download", "File M4A e MP4 scaricati"), 1)
        self.del_all = button("Elimina tutto", "danger", cb=self._confirm_clear)
        hr.addWidget(self.del_all, 0, Qt.AlignTop)
        lay.addLayout(hr)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Cerca per titolo o autore…")
        self.search.textChanged.connect(self.vm.set_search_query)
        lay.addWidget(self.search)
        fr = QHBoxLayout()
        self.filter_group = QButtonGroup(self)
        self.filter_btns = {}
        for key in (None, MediaFormat.MP3, MediaFormat.MP4):
            b = button("", "filter", cb=lambda _=False, k=key: self.vm.set_library_filter(k))
            b.setCheckable(True)
            self.filter_group.addButton(b)
            self.filter_btns[key] = b
            fr.addWidget(b)
        fr.addStretch()
        lay.addLayout(fr)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(8)
        lay.addLayout(self.list_box)
        lay.addStretch()
        self.vm.library_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        lib = self.vm.library
        na = sum(1 for i in lib if i.is_audio)
        self.filter_btns[None].setText(f"Tutti ({len(lib)})")
        self.filter_btns[MediaFormat.MP3].setText(f"Audio ({na})")
        self.filter_btns[MediaFormat.MP4].setText(f"MP4 ({len(lib) - na})")
        self.filter_btns[self.vm.library_filter].setChecked(True)
        self.del_all.setVisible(bool(lib))
        clear_layout(self.list_box)
        items = self.vm.filtered_library()
        if not lib:
            c, cl = card()
            cl.setAlignment(Qt.AlignCenter)
            e = label("📭", "title")
            e.setAlignment(Qt.AlignCenter)
            cl.addWidget(e)
            t = label("Nessun download completato", "section")
            t.setAlignment(Qt.AlignCenter)
            cl.addWidget(t)
            m = label("Incolla un link YouTube nella schermata di conversione per scaricare file M4A o MP4.",
                      "muted", wrap=True)
            m.setAlignment(Qt.AlignCenter)
            cl.addWidget(m)
            cl.addWidget(button("Vai al Convertitore", "primary", cb=lambda: self.win.go_tab(0)),
                         0, Qt.AlignCenter)
            self.list_box.addWidget(c)
            return
        if not items:
            c, cl = card()
            t = label("Nessun file con questo filtro", "section")
            t.setAlignment(Qt.AlignCenter)
            cl.addWidget(t)
            m = label("Prova a selezionare il filtro 'Tutti' per visualizzare tutti i file.", "muted", wrap=True)
            m.setAlignment(Qt.AlignCenter)
            cl.addWidget(m)
            self.list_box.addWidget(c)
            return
        for it in items:
            self.list_box.addWidget(DownloadedItemCard(
                it,
                on_play=lambda _=False, it=it: self.win.play_item(it),
                on_open=lambda _=False, it=it: open_external(it.file_path) or self.win.toast(
                    "Nessun player trovato per questo file"),
                on_reveal=lambda _=False, it=it: reveal_in_folder(it.file_path),
                on_delete=lambda _=False, it=it: self._confirm_delete(it)))

    def _confirm_delete(self, it: DownloadedItem):
        r = QMessageBox.question(self, "Elimina", f"Eliminare «{it.title}»?\nIl file verrà rimosso dal disco.")
        if r == QMessageBox.Yes:
            if self.win.audio.file_path == it.file_path:
                self.win.mini.close_player()
            self.vm.delete_downloaded_item(it)

    def _confirm_clear(self):
        r = QMessageBox.question(self, "Eliminare tutti i file?",
                                 "Questa operazione cancellerà tutti i brani e i video scaricati "
                                 "dalla memoria dell'app.")
        if r == QMessageBox.Yes:
            self.win.mini.close_player()
            self.vm.clear_all_library()


class SettingsScreen(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win, self.vm = win, win.vm
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa, lay = scroll_page()
        outer.addWidget(sa)
        lay.addWidget(header("Impostazioni & Info", "Configurazione cartella di download e statistiche"))

        c, cl = card()
        cl.addWidget(label("📁  Cartella di Salvataggio", "section"))
        cl.addWidget(label("I file M4A e MP4 verranno salvati qui", "muted"))
        self.folder_kind = label("", "ok")
        cl.addWidget(self.folder_kind)
        self.folder_path = label("", wrap=True)
        self.folder_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cl.addWidget(self.folder_path)
        r = QHBoxLayout()
        r.addWidget(button("Scegli cartella", "primary", cb=self._choose))
        self.reset_btn = button("Ripristina predefinita", cb=lambda: self.vm.set_folder(None))
        r.addWidget(self.reset_btn)
        r.addWidget(button("Apri cartella", cb=self._open_folder))
        r.addStretch()
        cl.addLayout(r)
        lay.addWidget(c)

        c, cl = card()
        cl.addWidget(label("💾  Spazio Utilizzato", "section"))
        self.stats_size = label("", "title")
        cl.addWidget(self.stats_size)
        self.stats_count = label("", "muted")
        cl.addWidget(self.stats_count)
        lay.addWidget(c)

        c, cl = card()
        cl.addWidget(label("⚖  Disclaimer & Note Legali", "section"))
        cl.addWidget(label(
            "TubeConvert è destinato esclusivamente al download e alla conversione di video di pubblico "
            "dominio, con licenza Creative Commons o per uso personale di backup. Rispetta sempre i diritti "
            "d'autore e i termini di servizio.", "muted", wrap=True))
        lay.addWidget(c)

        c, cl = card()
        cl.addWidget(label(APP_VERSION, "section"))
        cl.addWidget(label(
            "Applicazione per il download audio (M4A/AAC) e video H.264 (MP4) con player integrato e "
            "selezione della cartella di salvataggio.", "muted", wrap=True))
        lay.addWidget(c)
        lay.addStretch()

        self.vm.folder_changed.connect(self.refresh)
        self.vm.library_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        f = self.vm.folder()
        if f.is_default:
            self.folder_kind.setText("Cartella predefinita (Musica/Video)")
            self.folder_path.setText(f"Audio: {default_audio_dir()}\nVideo: {default_video_dir()}")
        else:
            self.folder_kind.setText("Cartella selezionata")
            self.folder_path.setText(f.path)
        self.reset_btn.setEnabled(not f.is_default)
        lib = self.vm.library
        total = sum(i.file_size for i in lib if os.path.exists(i.file_path))
        na = sum(1 for i in lib if i.is_audio)
        self.stats_size.setText(human_size(total))
        self.stats_count.setText(f"{len(lib)} file completati  •  {na} audio  •  {len(lib) - na} video")

    def _choose(self):
        cur = self.vm.folder().path or str(default_audio_dir().parent)
        d = QFileDialog.getExistingDirectory(self, "Scegli cartella", cur)
        if d:
            self.vm.set_folder(d)

    def _open_folder(self):
        f = self.vm.folder()
        p = f.path or str(default_audio_dir())
        os.makedirs(p, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))


# ================================================================ finestra
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TubeConvert")
        self.resize(940, 860)
        self.setMinimumSize(720, 600)
        self.vm = TubeConvertViewModel()
        self.audio = AudioPlayerManager()

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.toast_lbl = QLabel(root)
        self.toast_lbl.setStyleSheet(f"background:{SURFACE_VAR}; border:1px solid {PRIMARY}; "
                                     "border-radius:10px; padding:10px 14px;")
        self.toast_lbl.setWordWrap(True)
        self.toast_lbl.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast_lbl.hide)

        self.stack = QStackedWidget()
        self.converter = ConverterScreen(self)
        self.library = LibraryScreen(self)
        self.settings = SettingsScreen(self)
        for s in (self.converter, self.library, self.settings):
            self.stack.addWidget(s)
        v.addWidget(self.stack, 1)

        self.mini = MiniAudioPlayer(self.audio)
        self.mini.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.mini)

        nav = QFrame()
        self.nav = nav
        nav.setObjectName("nav")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(12, 8, 12, 8)
        self.nav_group = QButtonGroup(self)
        self.nav_btns = []
        for i, txt in enumerate(("⇩  Converti", "♫  Libreria", "⚙  Impostazioni")):
            b = button(txt, "navBtn", cb=lambda _=False, i=i: self.go_tab(i))
            b.setCheckable(True)
            self.nav_group.addButton(b)
            self.nav_btns.append(b)
            nl.addWidget(b)
        v.addWidget(nav)
        self.go_tab(0)
        self.vm.notice.connect(self.toast)

    def go_tab(self, i: int):
        self.stack.setCurrentIndex(i)
        self.nav_btns[i].setChecked(True)

    def toast(self, msg: str):
        self.toast_lbl.setText(msg)
        root = self.centralWidget()
        w = min(560, root.width() - 40)
        self.toast_lbl.setFixedWidth(w)
        self.toast_lbl.adjustSize()
        nav_h = self.nav.height() + (self.mini.height() if self.mini.isVisible() else 0)
        self.toast_lbl.move((root.width() - w) // 2, root.height() - nav_h - self.toast_lbl.height() - 16)
        self.toast_lbl.raise_()
        self.toast_lbl.show()
        self._toast_timer.start(3500)

    def open_video_dialog(self, title, video_id, file_path):
        if not file_path and not HAS_WEBENGINE:
            QDesktopServices.openUrl(QUrl("https://www.youtube.com/watch?v=" + video_id))
            return
        if self.audio.player.playbackState() == QMediaPlayer.PlayingState:
            self.audio.player.pause()
        VideoPlayerDialog(self, title, video_id, file_path).exec()

    def play_item(self, it: DownloadedItem):
        if not os.path.exists(it.file_path):
            self.toast("File non trovato sul dispositivo")
            return
        if it.is_audio:
            self.audio.play_track(it)
            self.mini.show_track()
        else:
            self.open_video_dialog(it.title, it.video_id, it.file_path)

    def play_task(self, t: ConversionTask):
        it = next((i for i in self.vm.library if i.file_path == t.output_file_path), None)
        if it:
            self.play_item(it)
        else:
            open_external(t.output_file_path)

    def closeEvent(self, e):
        if any(t.is_active for t in self.vm.tasks):
            r = QMessageBox.question(self, "TubeConvert",
                                     "Ci sono download in corso. Chiudere comunque e annullarli?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
        self.audio.stop()
        self.vm.shutdown()
        super().closeEvent(e)


def run():
    global THUMBS
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TubeConvert.Desktop")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("TubeConvert")
    app.setStyleSheet(STYLE)
    icon = os.path.join(os.path.dirname(__file__), "icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    THUMBS = ThumbnailLoader()
    w = MainWindow()
    w.show()
    return app.exec()
