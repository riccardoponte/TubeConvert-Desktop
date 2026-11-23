"""Stato dell'app e coda dei download (porting di TubeConvertViewModel.kt)."""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal

from .generator import CancelledError, MediaFileGenerator, error_message_for
from .models import (AudioQuality, ConversionTask, DownloadedItem, MediaFormat, TaskStatus,
                     VideoQuality)
from .storage import DownloadDao, FolderInfo, FolderPreferences
from .youtube import ParsedVideoInfo, extract_video_ids, fetch_video_info


class TubeConvertViewModel(QObject):
    parsed_changed = Signal()
    analyzing_changed = Signal(bool)
    tasks_changed = Signal()
    task_updated = Signal(str)
    library_changed = Signal()
    folder_changed = Signal()
    notice = Signal(str)
    selection_changed = Signal()

    _bg_parsed = Signal(int, list)
    _bg_progress = Signal(str, float, str, int, int, str)
    _bg_done = Signal(str, object, str)   # task_id, result|None, error

    def __init__(self):
        super().__init__()
        self.dao = DownloadDao()
        self.folder_prefs = FolderPreferences()
        self.generator = MediaFileGenerator()
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="tubeconvert")

        self.input_text = ""
        self.is_analyzing = False
        self.parsed_videos: list[ParsedVideoInfo] = []
        self._info_cache: dict[str, ParsedVideoInfo] = {}
        self._analyze_gen = 0

        self.selected_format = MediaFormat.MP3
        self.selected_audio_quality = AudioQuality.HIGH
        self.selected_video_quality = VideoQuality.P720

        self.tasks: list[ConversionTask] = []
        self._cancel: dict[str, threading.Event] = {}

        self.library: list[DownloadedItem] = self.dao.get_all()
        self.library_filter: MediaFormat | None = None
        self.search_query = ""

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(700)
        self._auto_timer.timeout.connect(self.analyze_links)

        self._bg_parsed.connect(self._on_parsed)
        self._bg_progress.connect(self._on_progress)
        self._bg_done.connect(self._on_done)

    # ----------------------------------------------------------- input/analysis
    def set_input_text(self, text: str):
        self.input_text = text
        self.schedule_auto_analyze()

    def schedule_auto_analyze(self):
        self._auto_timer.start()

    def analyze_links(self):
        self._auto_timer.stop()
        ids = extract_video_ids(self.input_text)
        self._analyze_gen += 1
        gen = self._analyze_gen
        if not ids:
            self.parsed_videos = []
            self._set_analyzing(False)
            self.parsed_changed.emit()
            return
        missing = [(v, u) for v, u in ids if v not in self._info_cache]
        if not missing:
            self.parsed_videos = [self._info_cache[v] for v, _ in ids]
            self.parsed_changed.emit()
            return
        self._set_analyzing(True)

        def work():
            for vid, url in missing:
                self._info_cache[vid] = fetch_video_info(vid, url)
            self._bg_parsed.emit(gen, [v for v, _ in ids])

        threading.Thread(target=work, daemon=True).start()

    def _on_parsed(self, gen: int, ids: list):
        if gen != self._analyze_gen:
            return
        self.parsed_videos = [self._info_cache[v] for v in ids if v in self._info_cache]
        self._set_analyzing(False)
        self.parsed_changed.emit()

    def _set_analyzing(self, v: bool):
        self.is_analyzing = v
        self.analyzing_changed.emit(v)

    def remove_parsed_video(self, video_id: str):
        self.parsed_videos = [p for p in self.parsed_videos if p.video_id != video_id]
        self.parsed_changed.emit()

    # ---------------------------------------------------------------- selection
    def select_format(self, f: MediaFormat):
        self.selected_format = f
        self.selection_changed.emit()

    def select_audio_quality(self, q: AudioQuality):
        self.selected_audio_quality = q
        self.selection_changed.emit()

    def select_video_quality(self, q: VideoQuality):
        self.selected_video_quality = q
        self.selection_changed.emit()

    # -------------------------------------------------------------------- tasks
    def start_conversion(self) -> bool:
        if not self.parsed_videos:
            ids = extract_video_ids(self.input_text)
            if not ids:
                self.notice.emit("Inserisci o incolla almeno un link YouTube valido prima di convertire.")
                return False
            self.parsed_videos = [self._info_cache.get(v) or ParsedVideoInfo(
                v, u, f"Video YouTube ({v})", "YouTube Creator", "https://www.youtube.com",
                f"https://img.youtube.com/vi/{v}/hqdefault.jpg") for v, u in ids]
        videos = list(self.parsed_videos)
        for p in videos:
            t = ConversionTask(
                video_id=p.video_id, original_url=p.original_url, title=p.title, author=p.author,
                author_url=p.author_url, thumbnail_url=p.thumbnail_url, format=self.selected_format,
                audio_quality=self.selected_audio_quality, video_quality=self.selected_video_quality)
            self.tasks.insert(0, t)
            self._process_task(t)
        self.notice.emit(f"Avviata conversione per {len(videos)} elemento/i")
        self.input_text = ""
        self.parsed_videos = []
        self.parsed_changed.emit()
        self.tasks_changed.emit()
        return True

    def _process_task(self, task: ConversionTask):
        ev = threading.Event()
        self._cancel[task.id] = ev
        task.status = TaskStatus.PENDING
        task.progress = 0.0
        task.error_message = ""
        task.speed_text = ""
        folder = self.folder_prefs.get().path

        def cb(progress, text, written, total, speed):
            self._bg_progress.emit(task.id, progress, text, written, total, speed)

        def job():
            try:
                res = self.generator.generate_media(task.video_id, task.title, task.format,
                                                    task.audio_quality, task.video_quality,
                                                    folder, cb, ev)
                self._bg_done.emit(task.id, res, "")
            except CancelledError:
                self._bg_done.emit(task.id, None, "__cancelled__")
            except Exception as e:  # noqa: BLE001
                self._bg_done.emit(task.id, None, error_message_for(e) or "Download non riuscito. Riprova.")

        self.pool.submit(job)

    def _find(self, task_id: str) -> ConversionTask | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def _on_progress(self, task_id, progress, text, written, total, speed):
        t = self._find(task_id)
        if not t or not t.is_active:
            return
        t.progress = progress
        t.status_text = text
        t.status = TaskStatus.DOWNLOADING if text.startswith("Download") else TaskStatus.EXTRACTING
        if written or total:
            t.downloaded_bytes, t.total_bytes = written, total
        if speed:
            t.speed_text = speed
        self.task_updated.emit(task_id)

    def _on_done(self, task_id, result, error):
        self._cancel.pop(task_id, None)
        t = self._find(task_id)
        if error == "__cancelled__":
            return
        if not t:
            return
        if result is None:
            t.status = TaskStatus.FAILED
            t.error_message = error
            t.speed_text = ""
            self.task_updated.emit(task_id)
            return
        t.status = TaskStatus.COMPLETED
        t.progress = 1.0
        t.output_file_path = result.path_or_uri
        t.total_bytes = t.downloaded_bytes = result.file_size
        t.speed_text = ""
        self.dao.insert(DownloadedItem(
            id=uuid.uuid4().hex, video_id=t.video_id, title=t.title, author=t.author,
            thumbnail_url=t.thumbnail_url, format=t.format.value, quality_label=t.quality_label,
            file_path=result.path_or_uri, file_size=result.file_size,
            downloaded_timestamp=int(time.time() * 1000)))
        self.reload_library()
        self.task_updated.emit(task_id)

    def cancel(self, task_id: str):
        ev = self._cancel.pop(task_id, None)
        if ev:
            ev.set()
        self.tasks = [t for t in self.tasks if t.id != task_id]
        self.tasks_changed.emit()

    def retry(self, task_id: str):
        t = self._find(task_id)
        if t and t.status is TaskStatus.FAILED:
            self._process_task(t)
            self.task_updated.emit(task_id)

    def remove_task(self, task_id: str):
        if any(t.id == task_id and t.is_active for t in self.tasks):
            return self.cancel(task_id)
        self.tasks = [t for t in self.tasks if t.id != task_id]
        self.tasks_changed.emit()

    def clear_completed_tasks(self):
        self.tasks = [t for t in self.tasks if t.is_active]
        self.tasks_changed.emit()

    # ------------------------------------------------------------------ library
    def reload_library(self):
        self.library = self.dao.get_all()
        self.library_changed.emit()

    def set_library_filter(self, f: MediaFormat | None):
        self.library_filter = f
        self.library_changed.emit()

    def set_search_query(self, q: str):
        self.search_query = q
        self.library_changed.emit()

    def filtered_library(self) -> list[DownloadedItem]:
        items = self.library
        if self.library_filter is not None:
            items = [i for i in items if i.format == self.library_filter.value]
        q = self.search_query.strip().lower()
        if q:
            items = [i for i in items if q in i.title.lower() or q in i.author.lower()]
        return items

    def delete_downloaded_item(self, item: DownloadedItem):
        try:
            if os.path.isfile(item.file_path):
                os.remove(item.file_path)
        except OSError:
            pass
        self.dao.delete_by_id(item.id)
        self.reload_library()

    def clear_all_library(self):
        for it in self.library:
            try:
                if os.path.isfile(it.file_path):
                    os.remove(it.file_path)
            except OSError:
                pass
        self.dao.delete_all()
        self.reload_library()

    # ------------------------------------------------------------------- folder
    def folder(self) -> FolderInfo:
        return self.folder_prefs.get()

    def set_folder(self, path: str | None):
        self.folder_prefs.set(path)
        self.folder_changed.emit()
        if path:
            self.notice.emit(f"Cartella di salvataggio impostata su: {path}")
        else:
            self.notice.emit("Cartella reimpostata su quella predefinita")

    def shutdown(self):
        for ev in self._cancel.values():
            ev.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
