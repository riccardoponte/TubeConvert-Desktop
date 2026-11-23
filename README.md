# TubeConvert Desktop

🇮🇹 [Italiano](#italiano) · 🇬🇧 [English](#english)

---

<a name="italiano"></a>
## 🇮🇹 Italiano

Versione Windows (Python + Qt) dell'app Android **TubeConvert** (`tube_converter.apk`, inclusa nel repository).
È stata ricostruita a partire dall'APK: stessi client InnerTube, stessa logica di download, stessi formati, stesse schermate e stessi messaggi.

### Avvio rapido — niente da installare

1. Scarica il repository (**Code → Download ZIP**, oppure `git clone`).
2. Doppio clic su **`TubeConvert.bat`**.

Python 3.14 e tutte le librerie sono già nella cartella `runtime/` (Python portatile ufficiale + PySide6, PyAV, requests).
`TubeConvert-debug.bat` avvia l'app con la console visibile, utile per leggere eventuali errori.

Requisiti: Windows 10/11 a 64 bit.

### Funzionalità

- Incolli uno o più link → analisi automatica con anteprima (titolo, autore, miniatura).
- **Audio M4A (AAC)** a 128 kbps o 48 kbps.
- **Video MP4 (H.264 + AAC)** a 1080p / 720p / 480p / 360p, con audio unito al video **senza ricodifica**.
- Coda multipla con stato, percentuale, MB trasferiti e velocità; annulla, riprova, pulisci completati.
- Salvataggio in `Musica\TubeConvert` / `Video\TubeConvert` oppure in una cartella a scelta.
- Libreria con ricerca, filtri (Tutti / Audio / MP4), player audio e video integrati, apertura esterna, eliminazione.
- Impostazioni: cartella di salvataggio, spazio utilizzato, note legali.

### Come funziona

| Modulo | Origine nell'APK | Ruolo |
|---|---|---|
| `tubeconvert/youtube.py` | `YouTubeParser`, `YouTubeStreamService` | metadati via oEmbed; `POST /youtubei/v1/player` con i client `ANDROID_VR 1.65.10` → `ANDROID_VR 1.62.27` → `ANDROID 21.26.364`; `visitorData` dalla risposta o dalla home page |
| `tubeconvert/generator.py` | `MediaFileGenerator` | Range request a blocchi; con 403 ripete forzando IPv4 e poi IPv6, poi cambia client; unione ed estrazione audio con PyAV in copia (al posto di `MediaMuxer`) |
| `tubeconvert/net.py` | `IpFamily`, `IpFamilyDns` | forzatura della famiglia di indirizzi |
| `tubeconvert/storage.py` | Room `AppDatabase`, `FolderPreferences` | SQLite (stessa tabella `downloads`) e preferenze in `%APPDATA%\TubeConvert` |
| `tubeconvert/viewmodel.py` | `TubeConvertViewModel` | coda, stato, libreria |
| `tubeconvert/ui.py` | `ConverterScreen`, `LibraryScreen`, `SettingsScreen`, componenti, `AudioPlayerManager` | interfaccia PySide6 |

### Struttura

```
TubeConvert.bat          avvio (Python portatile, senza console)
TubeConvert-debug.bat    avvio con console
main.py                  punto di ingresso
tubeconvert/             codice dell'applicazione
runtime/                 Python 3.14 portatile + librerie (Lib/site-packages)
requirements.txt         elenco delle librerie incluse
tube_converter.apk       app Android originale
README_APK.md            documentazione dell'app Android
```

Per aggiornare le librerie: `python -m pip install --target runtime\Lib\site-packages -r requirements.txt --upgrade`.

### Differenze rispetto ad Android

- "Condividi" è sostituito da **Mostra nella cartella** (Esplora file).
- La cartella si sceglie con la finestra di Windows invece che con Storage Access Framework.
- L'anteprima del video originale si apre nel browser: QtWebEngine non è incluso perché supera il limite di 100 MB per file di GitHub.
- La traccia M4A viene riscritta in un contenitore M4A standard, sempre senza ricodifica, per la massima compatibilità con i player di Windows.

### Limiti noti

Niente MP3 (solo AAC/M4A) e niente login. Se YouTube blocca l'IP della rete, tutti i client possono fallire: attendi qualche minuto, disattiva la VPN o cambia rete.

### Note legali

Scaricare contenuti protetti può violare i Termini di servizio di YouTube e il diritto d'autore. Usa l'app solo per contenuti di cui hai i diritti, di pubblico dominio o con licenza che ne consenta il download, e per uso personale. Progetto didattico, senza alcuna affiliazione con YouTube o Google.

---

<a name="english"></a>
## 🇬🇧 English

Windows (Python + Qt) version of the **TubeConvert** Android app (`tube_converter.apk`, included in the repository).
It was rebuilt from the APK: same InnerTube clients, same download logic, same formats, same screens and same messages (the UI is in Italian, like the original app).

### Quick start — nothing to install

1. Download the repository (**Code → Download ZIP**, or `git clone`).
2. Double-click **`TubeConvert.bat`**.

Python 3.14 and every library are already in the `runtime/` folder (official portable Python + PySide6, PyAV, requests).
`TubeConvert-debug.bat` starts the app with a visible console, useful to read any errors.

Requirements: 64-bit Windows 10/11.

### Features

- Paste one or more links → automatic analysis with preview (title, author, thumbnail).
- **M4A audio (AAC)** at 128 kbps or 48 kbps.
- **MP4 video (H.264 + AAC)** at 1080p / 720p / 480p / 360p, with audio merged into the video **without re-encoding**.
- Multi-item queue with status, percentage, transferred MB and speed; cancel, retry, clear completed.
- Saves to `Music\TubeConvert` / `Videos\TubeConvert` or to a folder of your choice.
- Library with search, filters (All / Audio / MP4), built-in audio and video players, open externally, delete.
- Settings: download folder, used space, legal notes.

### How it works

| Module | Origin in the APK | Role |
|---|---|---|
| `tubeconvert/youtube.py` | `YouTubeParser`, `YouTubeStreamService` | metadata via oEmbed; `POST /youtubei/v1/player` with clients `ANDROID_VR 1.65.10` → `ANDROID_VR 1.62.27` → `ANDROID 21.26.364`; `visitorData` from the response or the home page |
| `tubeconvert/generator.py` | `MediaFileGenerator` | chunked Range requests; on 403 retries forcing IPv4 then IPv6, then switches client; merging and audio extraction with PyAV in copy mode (instead of `MediaMuxer`) |
| `tubeconvert/net.py` | `IpFamily`, `IpFamilyDns` | forces the address family |
| `tubeconvert/storage.py` | Room `AppDatabase`, `FolderPreferences` | SQLite (same `downloads` table) and preferences in `%APPDATA%\TubeConvert` |
| `tubeconvert/viewmodel.py` | `TubeConvertViewModel` | queue, state, library |
| `tubeconvert/ui.py` | `ConverterScreen`, `LibraryScreen`, `SettingsScreen`, components, `AudioPlayerManager` | PySide6 user interface |

### Layout

```
TubeConvert.bat          launcher (portable Python, no console)
TubeConvert-debug.bat    launcher with console
main.py                  entry point
tubeconvert/             application code
runtime/                 portable Python 3.14 + libraries (Lib/site-packages)
requirements.txt         list of bundled libraries
tube_converter.apk       original Android app
README_APK.md            Android app documentation (Italian)
```

To update the libraries: `python -m pip install --target runtime\Lib\site-packages -r requirements.txt --upgrade`.

### Differences from Android

- "Share" is replaced by **Show in folder** (File Explorer).
- The folder is chosen with the Windows dialog instead of the Storage Access Framework.
- The original-video preview opens in the browser: QtWebEngine is not bundled because it exceeds GitHub's 100 MB per-file limit.
- The M4A track is rewritten into a standard M4A container, still without re-encoding, for maximum compatibility with Windows players.

### Known limitations

No MP3 (AAC/M4A only) and no login. If YouTube blocks the network's IP, every client may fail: wait a few minutes, turn off your VPN or switch network.

### Legal notice

Downloading protected content may violate YouTube's Terms of Service and copyright law. Use the app only for content you own the rights to, that is in the public domain, or whose license allows downloading, and for personal use. Educational project, not affiliated with YouTube or Google.
