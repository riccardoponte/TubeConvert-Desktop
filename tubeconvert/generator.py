"""Download dei byte, unione audio/video e salvataggio (porting di MediaFileGenerator.kt).

- Range request a blocchi con byte trasferiti e velocità.
- 403 -> ripete forzando IPv4 e poi IPv6; se persiste cambia client e
  rifà l'estrazione.
- Audio: traccia AAC dedicata; se c'è solo il progressivo estrae l'audio in
  M4A senza ricodifica.
- Video: traccia video H.264 + traccia AAC unite senza ricodifica; ripiego sul
  flusso progressivo (in genere 360p).
L'unione/estrazione usa PyAV (librerie FFmpeg) in modalità copia, equivalente di MediaMuxer.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from . import net
from .models import AudioQuality, MediaFormat, VideoQuality
from .storage import default_audio_dir, default_video_dir
from .youtube import (DownloadException, HttpDownloadException, LoginRequiredException,
                      StreamInfo, YouTubeStreamService)

# on_progress(progress 0..1, status_text, downloaded_bytes, total_bytes, speed_text)
ProgressCb = Callable[[float, str, int, int, str], None]

CHUNK_SIZE = 10 * 1024 * 1024      # dimensione di ogni Range request
READ_BUFFER = 64 * 1024


class CancelledError(Exception):
    pass


@dataclass
class GeneratedMediaResult:
    path_or_uri: str
    file_size: int


def sanitize_title(title: str) -> str:
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", title)
    t = re.sub(r"\s+", " ", t).strip().rstrip(".")
    return (t[:120] or "TubeConvert")


def transfer_summary(written: int, total: int, kb_per_second: float) -> str:
    mb = written / (1024 * 1024)
    if total > 0:
        return f"{mb:.1f} MB / {total / (1024 * 1024):.1f} MB • {kb_per_second:.0f} KB/s"
    return f"{mb:.1f} MB • {kb_per_second:.0f} KB/s"


class MediaFileGenerator:
    def __init__(self):
        self.streams = YouTubeStreamService()

    # ------------------------------------------------------------------ select
    @staticmethod
    def best_audio(streams: list[StreamInfo], quality: AudioQuality) -> StreamInfo | None:
        tracks = [s for s in streams if s.mime_type == "audio/mp4" and not s.progressive]
        if not tracks:
            return None
        if quality is AudioQuality.LOW:
            return min(tracks, key=lambda s: s.bitrate)
        return max(tracks, key=lambda s: s.bitrate)

    @staticmethod
    def best_video(streams: list[StreamInfo], quality: VideoQuality) -> StreamInfo | None:
        vids = [s for s in streams if s.mime_type == "video/mp4" and not s.progressive
                and s.codecs.startswith("avc1")]
        if not vids:
            return None
        under = [s for s in vids if s.height <= quality.height]
        pool = under or [min(vids, key=lambda s: s.height)]
        return max(pool, key=lambda s: (s.height, s.bitrate))

    @staticmethod
    def best_progressive(streams: list[StreamInfo], target_height: int) -> StreamInfo | None:
        cands = [s for s in streams if s.progressive and s.mime_type == "video/mp4"]
        if not cands:
            return None
        under = [s for s in cands if s.height <= target_height] or cands
        return max(under, key=lambda s: (s.height, s.bitrate))

    # ---------------------------------------------------------------- download
    def _download_once(self, stream: StreamInfo, dest: Path, family: net.IpFamily,
                       p_start: float, p_end: float, label: str,
                       on_progress: ProgressCb, cancel: threading.Event):
        total = stream.content_length
        written = 0
        started = time.monotonic()
        last_update = 0.0
        session = net.session_for_family(family)
        headers = {"User-Agent": stream.user_agent, "Accept": "*/*",
                   "Origin": "https://www.youtube.com", "Referer": "https://www.youtube.com/"}
        with net.use_family(family), open(dest, "wb") as out:
            while True:
                if cancel.is_set():
                    raise CancelledError()
                end = written + CHUNK_SIZE - 1
                if total > 0:
                    end = min(end, total - 1)
                h = dict(headers, Range=f"bytes={written}-{end}")
                try:
                    r = session.get(stream.url, headers=h, stream=True, timeout=(15, 30))
                except requests.RequestException as e:
                    raise DownloadException(f"Download non riuscito: {e}") from e
                with r:
                    if r.status_code == 403:
                        raise HttpDownloadException(403, "YouTube ha bloccato il download (403). "
                                                    "Se usi una VPN, disattivala e riprova.")
                    if r.status_code in (404, 410):
                        raise HttpDownloadException(r.status_code,
                                                    f"Il flusso del video è scaduto ({r.status_code}). Riavvia il download.")
                    if r.status_code == 416:  # oltre la fine del file
                        break
                    if not r.ok:
                        snippet = (r.text or "")[:120] if r.headers.get("content-type", "").startswith("text") else ""
                        raise HttpDownloadException(
                            r.status_code, f"YouTube ha rifiutato il download ({r.status_code})."
                            + (f" Dettaglio: {snippet}" if snippet else ""))
                    if total <= 0:
                        cr = r.headers.get("Content-Range", "")
                        m = re.search(r"/(\d+)$", cr)
                        if m:
                            total = int(m.group(1))
                    got = 0
                    for buf in r.iter_content(READ_BUFFER):
                        if cancel.is_set():
                            raise CancelledError()
                        out.write(buf)
                        written += len(buf)
                        got += len(buf)
                        now = time.monotonic()
                        if now - last_update > 0.25:
                            last_update = now
                            elapsed = max(now - started, 0.001)
                            kbps = written / 1024 / elapsed
                            frac = written / total if total > 0 else 0.0
                            on_progress(p_start + (p_end - p_start) * min(frac, 1.0), label,
                                        written, total, transfer_summary(written, total, kbps))
                    if r.status_code == 200:  # server ha ignorato il Range: file completo
                        break
                if got == 0 or (total > 0 and written >= total):
                    break
        if written == 0:
            raise DownloadException("Risposta di YouTube vuota.")
        elapsed = max(time.monotonic() - started, 0.001)
        on_progress(p_end, label, written, total or written,
                    transfer_summary(written, total or written, written / 1024 / elapsed))

    def download_stream(self, stream: StreamInfo, dest: Path, p_start: float, p_end: float,
                        label: str, on_progress: ProgressCb, cancel: threading.Event):
        last: HttpDownloadException | None = None
        for family in (net.IpFamily.ANY, net.IpFamily.IPV4, net.IpFamily.IPV6):
            try:
                self._download_once(stream, dest, family, p_start, p_end, label, on_progress, cancel)
                return
            except HttpDownloadException as e:
                if e.code != 403:
                    raise
                last = e
            except DownloadException:
                if family is net.IpFamily.ANY:
                    raise
                # famiglia non disponibile (es. niente IPv6): prova la successiva
                continue
        raise last or HttpDownloadException(403, "YouTube ha bloccato il download. "
                                                 "Riprova tra qualche minuto o cambia rete.")

    # ------------------------------------------------------------ remux (PyAV)
    @staticmethod
    def _remux(sources: list[tuple[Path, str]], out: Path, cancel: threading.Event):
        """Copia (senza ricodifica) una traccia per ogni sorgente in un MP4/M4A,
        interlacciando i pacchetti per tempo: equivalente di MediaMuxer."""
        import av
        inputs, pairs = [], []
        try:
            for path, kind in sources:
                c = av.open(str(path))
                inputs.append(c)
                streams = c.streams.video if kind == "video" else c.streams.audio
                if not streams:
                    raise DownloadException("Traccia audio assente nel video." if kind == "audio"
                                            else "Tracce audio/video non valide.")
                pairs.append((c, streams[0]))
            fmt = "ipod" if out.suffix == ".m4a" else "mp4"
            with av.open(str(out), "w", format=fmt, options={"movflags": "+faststart"}) as oc:
                gens = []
                for c, st in pairs:
                    o = oc.add_stream_from_template(st)
                    gens.append((c.demux(st), o, st.time_base))
                heads = []
                for g, o, tb in gens:
                    heads.append(next((pk for pk in g if pk.dts is not None), None))
                n = 0
                while any(h is not None for h in heads):
                    i = min((k for k, h in enumerate(heads) if h is not None),
                            key=lambda k: float(heads[k].dts * gens[k][2]))
                    pkt = heads[i]
                    pkt.stream = gens[i][1]
                    oc.mux(pkt)
                    heads[i] = next((pk for pk in gens[i][0] if pk.dts is not None), None)
                    n += 1
                    if n % 500 == 0 and cancel.is_set():
                        raise CancelledError()
        except (CancelledError, DownloadException):
            raise
        except Exception as e:  # noqa: BLE001
            raise DownloadException(str(e)) from e
        finally:
            for c in inputs:
                c.close()

    def mux_tracks(self, video: Path, audio: Path, out: Path, cancel: threading.Event):
        try:
            self._remux([(video, "video"), (audio, "audio")], out, cancel)
        except DownloadException as e:
            raise DownloadException("Tracce audio/video non valide.") from e

    def extract_audio_track(self, source: Path, out: Path, cancel: threading.Event):
        try:
            self._remux([(source, "audio")], out, cancel)
        except DownloadException as e:
            raise DownloadException("Impossibile estrarre la traccia audio da questo video.") from e

    # ----------------------------------------------------------------- produce
    def _download_audio(self, streams, quality, work: Path, on_progress, cancel) -> Path:
        direct = self.best_audio(streams, quality)
        if direct:
            f = work / "audio.m4a"
            self.download_stream(direct, f, 0.05, 0.92, "Download file...", on_progress, cancel)
            # la traccia DASH viene riscritta come M4A standard (senza ricodifica)
            fixed = work / "audio_m4a.m4a"
            try:
                self.extract_audio_track(f, fixed, cancel)
                return fixed
            except DownloadException:
                return f
        prog = self.best_progressive(streams, 360)
        if not prog:
            raise DownloadException("Nessuna traccia audio disponibile per questo video.")
        src = work / "sorgente.mp4"
        self.download_stream(prog, src, 0.05, 0.85, "Download file...", on_progress, cancel)
        on_progress(0.9, "Estrazione audio…", 0, 0, "")
        f = work / "audio_estratto.m4a"
        self.extract_audio_track(src, f, cancel)
        return f

    def _download_video(self, streams, quality, work: Path, on_progress, cancel) -> Path:
        video = self.best_video(streams, quality)
        audio = self.best_audio(streams, AudioQuality.HIGH)
        if video and audio:
            vf, af = work / "video.mp4", work / "audio.m4a"
            self.download_stream(video, vf, 0.05, 0.70, "Download file...", on_progress, cancel)
            self.download_stream(audio, af, 0.70, 0.90, "Download file...", on_progress, cancel)
            on_progress(0.93, "Unione audio e video…", 0, 0, "")
            out = work / "unito.mp4"
            try:
                self.mux_tracks(vf, af, out, cancel)
                return out
            except DownloadException:
                pass  # ripiego sul progressivo
        prog = self.best_progressive(streams, quality.height)
        if not prog:
            raise DownloadException("Nessun flusso video compatibile disponibile per questo video.")
        f = work / "sorgente.mp4"
        self.download_stream(prog, f, 0.05, 0.95, "Download file...", on_progress, cancel)
        return f

    def save_to_destination(self, src: Path, title: str, fmt: MediaFormat, folder: str | None) -> Path:
        if folder:
            target_dir = Path(folder)
        else:
            target_dir = default_audio_dir() if fmt is MediaFormat.MP3 else default_video_dir()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise DownloadException("Impossibile creare il file nella cartella selezionata.") from e
        base = sanitize_title(title)
        dest = target_dir / f"{base}{fmt.extension}"
        n = 1
        while dest.exists():
            dest = target_dir / f"{base} ({n}){fmt.extension}"
            n += 1
        try:
            shutil.move(str(src), str(dest))
        except OSError as e:
            raise DownloadException("Impossibile aprire il file di destinazione.") from e
        return dest

    def generate_media(self, video_id: str, title: str, fmt: MediaFormat,
                       audio_quality: AudioQuality, video_quality: VideoQuality,
                       folder: str | None, on_progress: ProgressCb,
                       cancel: threading.Event) -> GeneratedMediaResult:
        work = Path(tempfile.mkdtemp(prefix="tubeconvert_"))
        used_profiles: set[str] = set()
        last_error: Exception | None = None
        try:
            on_progress(0.02, "Conversione in corso...", 0, 0, "")
            while True:
                if cancel.is_set():
                    raise CancelledError()
                try:
                    ps = self.streams.fetch_streams(video_id, used_profiles)
                except DownloadException as e:
                    if last_error is not None:
                        raise last_error from e
                    raise
                used_profiles.add(ps.profile_name)
                try:
                    if fmt is MediaFormat.MP3:
                        produced = self._download_audio(ps.streams, audio_quality, work, on_progress, cancel)
                    else:
                        produced = self._download_video(ps.streams, video_quality, work, on_progress, cancel)
                    break
                except HttpDownloadException as e:
                    if e.code != 403:
                        raise
                    last_error = e  # blocco per client: cambia client e rifai l'estrazione
                    for f in work.iterdir():
                        f.unlink(missing_ok=True)
                    on_progress(0.02, "Conversione in corso...", 0, 0, "")
            on_progress(0.97, "Salvataggio…", 0, 0, "")
            dest = self.save_to_destination(produced, title, fmt, folder)
            size = dest.stat().st_size
            on_progress(1.0, "Completato", size, size, "")
            return GeneratedMediaResult(str(dest), size)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def error_message_for(e: Exception) -> str:
    if isinstance(e, (DownloadException, LoginRequiredException)):
        return str(e)
    return f"Errore durante la conversione: {e}"
