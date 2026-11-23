"""Estrazione metadati e flussi da YouTube (porting di YouTubeParser.kt e
YouTubeStreamService in MediaFileGenerator.kt).

- Metadati: endpoint oEmbed (titolo, autore, miniatura) con ripiego sulla
  miniatura img.youtube.com/vi/<id>/hqdefault.jpg.
- Flussi: endpoint InnerTube /youtubei/v1/player con i client
  ANDROID_VR 1.65.10 -> ANDROID_VR 1.62.27 -> ANDROID 21.26.364.
"""
from __future__ import annotations

import re
import threading
import urllib.parse
from dataclasses import dataclass, field

import requests


YOUTUBE_URL_REGEX = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/|v/)|youtu\.be/|"
    r"music\.youtube\.com/watch\?(?:.*&)?v=)([a-zA-Z0-9_-]{11})"
)
VIDEO_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{11}$")
VISITOR_DATA_REGEXES = [
    re.compile(r'"visitorData":"([^"]+)"'),
    re.compile(r'"VISITOR_DATA":"([^"]+)"'),
]

PLAYER_ENDPOINT = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
HOME_ENDPOINT = "https://www.youtube.com/"
WATCH_ENDPOINT = "https://www.youtube.com/watch?v="

BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
]
ACCEPT_LANGUAGE = "it-IT,it;q=0.9,en;q=0.8"


# --------------------------------------------------------------------------
# Eccezioni
# --------------------------------------------------------------------------
class DownloadException(Exception):
    """Errore con messaggio in italiano mostrabile all'utente."""


class LoginRequiredException(DownloadException):
    pass


class HttpDownloadException(DownloadException):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# Metadati
# --------------------------------------------------------------------------
@dataclass
class ParsedVideoInfo:
    video_id: str
    original_url: str
    title: str
    author: str
    author_url: str
    thumbnail_url: str


def default_thumbnail(video_id: str) -> str:
    return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"


def extract_video_ids(text: str) -> list[tuple[str, str]]:
    """Restituisce [(video_id, url_originale)] senza duplicati, nell'ordine."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for token in re.split(r"\s+", text.strip()):
        if not token:
            continue
        vid = None
        m = YOUTUBE_URL_REGEX.search(token)
        if m:
            vid = m.group(1)
        elif VIDEO_ID_REGEX.match(token):
            vid = token
        if vid and vid not in seen:
            seen.add(vid)
            out.append((vid, token if m else WATCH_ENDPOINT + vid))
    return out


def fetch_video_info(video_id: str, original_url: str | None = None) -> ParsedVideoInfo:
    standard_url = WATCH_ENDPOINT + video_id
    title, author, author_url, thumb = "", "", "", ""
    try:
        o_embed = ("https://www.youtube.com/oembed?url="
                   + urllib.parse.quote(standard_url, safe="") + "&format=json")
        r = requests.get(o_embed, timeout=15, headers={
            "User-Agent": BROWSER_USER_AGENTS[0], "Accept-Language": ACCEPT_LANGUAGE})
        if r.ok:
            j = r.json()
            title = j.get("title", "") or ""
            author = j.get("author_name", "") or ""
            author_url = j.get("author_url", "") or ""
            thumb = j.get("thumbnail_url", "") or ""
    except Exception:
        pass
    return ParsedVideoInfo(
        video_id=video_id,
        original_url=original_url or standard_url,
        title=title.strip() or f"Video YouTube ({video_id})",
        author=author.strip() or "YouTube Creator",
        author_url=author_url or "https://www.youtube.com",
        thumbnail_url=thumb or default_thumbnail(video_id),
    )


# --------------------------------------------------------------------------
# Flussi
# --------------------------------------------------------------------------
@dataclass
class StreamInfo:
    itag: int
    url: str
    mime_type: str
    bitrate: int
    height: int
    quality_label: str
    content_length: int
    progressive: bool
    user_agent: str
    codecs: str = ""

    @property
    def is_audio(self) -> bool:
        return self.mime_type.startswith("audio/")

    @property
    def is_video(self) -> bool:
        return self.mime_type.startswith("video/")


@dataclass
class ClientProfile:
    name: str
    client_name: str
    version: str
    user_agent: str
    extra: dict = field(default_factory=dict)


PROFILES = [
    ClientProfile(
        name="ANDROID_VR 1.65.10", client_name="ANDROID_VR", version="1.65.10",
        user_agent="com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12; en_US) gzip",
        extra={"deviceMake": "Oculus", "deviceModel": "Quest 3",
               "androidSdkVersion": 32, "osName": "Android", "osVersion": "12"},
    ),
    ClientProfile(
        name="ANDROID_VR 1.62.27", client_name="ANDROID_VR", version="1.62.27",
        user_agent="com.google.android.apps.youtube.vr.oculus/1.62.27 (Linux; U; Android 12; en_US) gzip",
        extra={"deviceMake": "Oculus", "deviceModel": "Quest 3",
               "androidSdkVersion": 32, "osName": "Android", "osVersion": "12"},
    ),
    ClientProfile(
        name="ANDROID 21.26.364", client_name="ANDROID", version="21.26.364",
        user_agent="com.google.android.youtube/21.26.364 (Linux; U; Android 11) gzip",
        extra={"androidSdkVersion": 30, "osName": "Android", "osVersion": "11"},
    ),
]


@dataclass
class ProfileStreams:
    profile_name: str
    streams: list[StreamInfo]


class YouTubeStreamService:
    def __init__(self):
        self._lock = threading.Lock()
        self._cached_visitor: str | None = None

    # ---- visitorData ------------------------------------------------------
    def ensure_visitor_data(self, force_refresh: bool = False) -> str | None:
        with self._lock:
            if self._cached_visitor and not force_refresh:
                return self._cached_visitor
        visitor = None
        for ua in BROWSER_USER_AGENTS:
            try:
                r = requests.get(HOME_ENDPOINT, timeout=15, headers={
                    "User-Agent": ua, "Accept-Language": ACCEPT_LANGUAGE,
                    "Cookie": "SOCS=CAI"})
                html = r.text
                for rx in VISITOR_DATA_REGEXES:
                    m = rx.search(html)
                    if m:
                        visitor = m.group(1)
                        break
            except Exception:
                continue
            if visitor:
                break
        if visitor:
            visitor = visitor.replace("\\u003d", "=").replace("%3D", "=")
            with self._lock:
                self._cached_visitor = visitor
        return visitor

    def _store_visitor(self, v: str | None):
        if v:
            with self._lock:
                self._cached_visitor = v

    # ---- player request ---------------------------------------------------
    def player_request(self, video_id: str, profile: ClientProfile, visitor: str | None) -> dict:
        client = {"clientName": profile.client_name, "clientVersion": profile.version,
                  "hl": "it", "gl": "IT", **profile.extra}
        if visitor:
            client["visitorData"] = visitor
        payload = {
            "context": {"client": client},
            "videoId": video_id,
            "contentCheckOk": True,
            "racyCheckOk": True,
        }
        headers = {
            "User-Agent": profile.user_agent,
            "Content-Type": "application/json",
            "Accept-Language": ACCEPT_LANGUAGE,
            "Origin": "https://www.youtube.com",
            "Referer": WATCH_ENDPOINT + video_id,
            "Cookie": "SOCS=CAI",
        }
        if visitor:
            headers["X-Goog-Visitor-Id"] = visitor
        try:
            r = requests.post(PLAYER_ENDPOINT, json=payload, headers=headers, timeout=20)
        except requests.RequestException as e:
            raise DownloadException(f"Impossibile interrogare YouTube ({e}).") from e
        if not r.ok:
            raise HttpDownloadException(r.status_code, f"Impossibile interrogare YouTube ({r.status_code}).")
        if not r.text.strip():
            raise DownloadException("Risposta di YouTube vuota.")
        return r.json()

    @staticmethod
    def explain_playability(status: dict) -> str:
        reason = (status.get("reason") or "").strip() or "motivo sconosciuto"
        sub = status.get("errorScreen", {}).get("playerErrorMessageRenderer", {}) \
            .get("subreason", {}).get("simpleText", "")
        return reason + (f" ({sub})" if sub else "")

    @staticmethod
    def collect_streams(json_resp: dict, user_agent: str) -> list[StreamInfo]:
        sd = json_resp.get("streamingData") or {}
        out: list[StreamInfo] = []
        for key, progressive in (("formats", True), ("adaptiveFormats", False)):
            for f in sd.get(key) or []:
                url = f.get("url")
                if not url:  # signatureCipher non supportato
                    continue
                full_mime = f.get("mimeType") or ""
                mime = full_mime.split(";")[0].strip()
                cm = re.search(r'codecs="([^"]+)"', full_mime)
                out.append(StreamInfo(
                    itag=int(f.get("itag", 0)), url=url, mime_type=mime,
                    bitrate=int(f.get("bitrate", 0) or 0),
                    height=int(f.get("height", 0) or 0),
                    quality_label=f.get("qualityLabel", "") or "",
                    content_length=int(f.get("contentLength", 0) or 0),
                    progressive=progressive, user_agent=user_agent,
                    codecs=cm.group(1) if cm else "",
                ))
        return out

    def fetch_streams_with_profile(self, video_id: str, profile: ClientProfile,
                                   force_visitor_refresh: bool = False) -> list[StreamInfo]:
        visitor = self.ensure_visitor_data(force_visitor_refresh)
        j = self.player_request(video_id, profile, visitor)
        self._store_visitor((j.get("responseContext") or {}).get("visitorData"))
        status = j.get("playabilityStatus") or {}
        st = status.get("status", "OK")
        if st == "LOGIN_REQUIRED":
            raise LoginRequiredException(
                "YouTube chiede un accesso per questo video (controllo anti-bot). "
                "Riprova più tardi, anche da rete mobile/Wi-Fi diversa.")
        if st in ("UNPLAYABLE", "ERROR", "LIVE_STREAM_OFFLINE"):
            raise DownloadException("Video non disponibile: " + self.explain_playability(status))
        if st != "OK":
            raise DownloadException("Questo video non può essere scaricato: "
                                    + self.explain_playability(status))
        streams = self.collect_streams(j, profile.user_agent)
        if not streams:
            raise DownloadException("YouTube non ha restituito flussi scaricabili per questo video.")
        return streams

    def fetch_streams(self, video_id: str, skip_profiles: set[str] | None = None) -> ProfileStreams:
        """Prova i client nell'ordine e restituisce il primo che fornisce flussi."""
        skip = skip_profiles or set()
        last_error: Exception | None = None
        for profile in PROFILES:
            if profile.name in skip:
                continue
            for attempt in range(2):
                try:
                    streams = self.fetch_streams_with_profile(video_id, profile, force_visitor_refresh=attempt > 0)
                    return ProfileStreams(profile.name, streams)
                except LoginRequiredException as e:
                    last_error = e
                    continue  # riprova con visitorData rinnovato, poi client successivo
                except DownloadException as e:
                    last_error = e
                    break
        if last_error:
            raise last_error
        raise DownloadException("YouTube non ha restituito nessun flusso scaricabile per questo video.")

