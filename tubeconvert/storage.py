"""Persistenza: database dei download (porting di Room AppDatabase/DownloadDao)
e preferenze della cartella (porting di FolderPreferences)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from .models import DownloadedItem


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / "TubeConvert"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _known_folder(name: str, fallback: str) -> Path:
    """Music / Videos dell'utente (con supporto alle cartelle spostate su OneDrive)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            guids = {
                "Music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
                "Videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
            }
            import uuid as _uuid
            g = _uuid.UUID(guids[name])

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]
            guid = GUID(g.fields[0], g.fields[1], g.fields[2],
                        (wintypes.BYTE * 8).from_buffer_copy(g.bytes[8:]))
            p = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(p)) == 0:
                res = Path(p.value)
                ctypes.windll.ole32.CoTaskMemFree(p)
                return res
        except Exception:
            pass
    return Path.home() / fallback


def default_audio_dir() -> Path:
    return _known_folder("Music", "Music") / "TubeConvert"


def default_video_dir() -> Path:
    return _known_folder("Videos", "Videos") / "TubeConvert"


# --------------------------------------------------------------------------
class DownloadDao:
    SCHEMA = (
        "CREATE TABLE IF NOT EXISTS `downloads` (`id` TEXT NOT NULL, `videoId` TEXT NOT NULL, "
        "`title` TEXT NOT NULL, `author` TEXT NOT NULL, `thumbnailUrl` TEXT NOT NULL, "
        "`format` TEXT NOT NULL, `qualityLabel` TEXT NOT NULL, `filePath` TEXT NOT NULL, "
        "`fileSize` INTEGER NOT NULL, `downloadedTimestamp` INTEGER NOT NULL, PRIMARY KEY(`id`))"
    )

    def __init__(self, path: Path | None = None):
        self.path = path or (app_data_dir() / "tubeconvert.db")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(self.SCHEMA)
        self._conn.commit()

    def get_all(self) -> list[DownloadedItem]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, videoId, title, author, thumbnailUrl, format, qualityLabel, filePath, "
                "fileSize, downloadedTimestamp FROM downloads ORDER BY downloadedTimestamp DESC").fetchall()
        return [DownloadedItem(*r) for r in rows]

    def insert(self, it: DownloadedItem):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO `downloads` (`id`,`videoId`,`title`,`author`,`thumbnailUrl`,"
                "`format`,`qualityLabel`,`filePath`,`fileSize`,`downloadedTimestamp`) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (it.id, it.video_id, it.title, it.author, it.thumbnail_url, it.format,
                 it.quality_label, it.file_path, it.file_size, it.downloaded_timestamp))
            self._conn.commit()

    def delete_by_id(self, item_id: str):
        with self._lock:
            self._conn.execute("DELETE FROM downloads WHERE id = ?", (item_id,))
            self._conn.commit()

    def delete_all(self):
        with self._lock:
            self._conn.execute("DELETE FROM downloads")
            self._conn.commit()


# --------------------------------------------------------------------------
@dataclass
class FolderInfo:
    path: str | None        # None = cartella predefinita (Music/Videos)

    @property
    def is_default(self) -> bool:
        return not self.path

    @property
    def display_name(self) -> str:
        if self.is_default:
            return "Predefinita (Musica e Video/TubeConvert)"
        return self.path or ""


class FolderPreferences:
    def __init__(self):
        self.file = app_data_dir() / "preferences.json"

    def _load(self) -> dict:
        try:
            return json.loads(self.file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def get(self) -> FolderInfo:
        return FolderInfo(self._load().get("customFolder") or None)

    def set(self, path: str | None):
        d = self._load()
        d["customFolder"] = path
        self.file.write_text(json.dumps(d, indent=2), encoding="utf-8")
