"""Modelli (porting di model/MediaModels.kt)."""
from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field


class MediaFormat(enum.Enum):
    MP3 = "MP3"   # nome storico: il file prodotto è M4A/AAC
    MP4 = "MP4"

    @property
    def label(self) -> str:
        return "Audio M4A" if self is MediaFormat.MP3 else "Video MP4"

    @property
    def extension(self) -> str:
        return ".m4a" if self is MediaFormat.MP3 else ".mp4"


class AudioQuality(enum.Enum):
    HIGH = ("128 kbps", "Qualità originale AAC")
    LOW = ("48 kbps", "File più leggero")

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def description(self) -> str:
        return self.value[1]


class VideoQuality(enum.Enum):
    P1080 = ("1080p", "Full HD", 1080)
    P720 = ("720p", "HD", 720)
    P480 = ("480p", "SD", 480)
    P360 = ("360p", "Leggero", 360)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def description(self) -> str:
        return self.value[1]

    @property
    def height(self) -> int:
        return self.value[2]


class TaskStatus(enum.Enum):
    PENDING = "In coda"
    EXTRACTING = "Conversione in corso..."
    DOWNLOADING = "Download file..."
    COMPLETED = "Completato"
    FAILED = "Fallito"


@dataclass
class ConversionTask:
    video_id: str
    original_url: str
    title: str
    author: str
    author_url: str
    thumbnail_url: str
    format: MediaFormat
    audio_quality: AudioQuality
    video_quality: VideoQuality
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    status_text: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_text: str = ""
    error_message: str = ""
    output_file_path: str = ""
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def quality_label(self) -> str:
        return self.audio_quality.label if self.format is MediaFormat.MP3 else self.video_quality.label

    @property
    def is_active(self) -> bool:
        return self.status in (TaskStatus.PENDING, TaskStatus.EXTRACTING, TaskStatus.DOWNLOADING)


@dataclass
class DownloadedItem:
    id: str
    video_id: str
    title: str
    author: str
    thumbnail_url: str
    format: str          # "MP3" (audio m4a) | "MP4"
    quality_label: str
    file_path: str
    file_size: int
    downloaded_timestamp: int

    @property
    def is_audio(self) -> bool:
        return self.format == MediaFormat.MP3.value
