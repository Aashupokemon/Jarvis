# J.A.R.V.I.S — AI Laptop Assistant
### Powered by Claude AI · Phases 1-4 complete

A voice and text-controlled AI assistant that runs on your laptop.
Talk to it naturally — it understands commands, remembers context,
runs custom routines, and can even look at your screen.

---

## Quick Start

```bash
bash setup.sh
# Or manually:
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python jarvis.py          # terminal mode
python jarvis_tray.py     # background tray mode (Phase 4)
```

---

## Architecture overview

| File | Purpose |
|---|---|
| `jarvis.py` | Core engine — voice, AI brain, commands, memory, skills, plugins, wake word |
| `jarvis_tray.py` | Phase 4 — runs Jarvis in the system tray instead of a terminal |
| `email_calendar.py` | Phase 4 — Gmail + Google Calendar integration |
| `screen_vision.py` | Phase 4 — lets Jarvis see and describe your screen |
| `config.json` | All tunable settings (wake word, voice speed, model, etc.) |
| `skills.json` | Your custom multi-step voice routines |
| `plugins/` | Drop-in `.py` files that extend Jarvis with new commands |
| `memory.json` | Auto-generated — persistent conversation history + facts |

---

## Phase 1 & 2 — Core + Automation

### System Info
| Say | Does |
|---|---|
| "What time is it?" | Tells you the current time |
| "Battery status" | Battery % and time remaining |
| "CPU performance" | CPU, RAM, disk usage |
| "Weather in Mumbai" | Fetches current weather |
| "Uptime" | How long the system has been running |

### App & System Control
| Say | Does |
|---|---|
| "Open Chrome" | Opens any installed app |
| "Close Spotify" | Terminates the process |
| "Volume up / down / mute" | Controls system volume |
| "Take a screenshot" | Saves to ~/Pictures |
| "Lock screen" | Locks your computer |
| "Sleep" | Suspends the laptop |

### Web & Files
| Say | Does |
|---|---|
| "Search Python tutorials" | Opens Google search |
| "YouTube lo-fi music" | Searches YouTube |
| "Create file notes.txt" | Creates file in home folder |
| "List files in Documents" | Lists folder contents |

---

## Phase 3 — Wake Word, Memory, Skills, Plugins

### Wake Word
Say **"Hey Jarvis"** anytime — no button press needed. Jarvis listens in the
background using a lightweight Whisper-based detector (default `simple` engine,
zero extra setup) or an optional **Porcupine** engine for lower CPU usage and
higher accuracy (needs a free key from console.picovoice.ai — set it in
`config.json` under `porcupine_access_key` and `wake_word_engine: "porcupine"`).

### Persistent Memory
Conversations and facts survive restarts, saved to `memory.json`.

| Say | Does |
|---|---|
| "Remember that my name is Arjun" | Saves a fact |
| "What do you remember?" | Summarizes stored facts and history |
| "Who am I?" | Recalls your name |
| "Clear memory" | Wipes everything and starts fresh |

### Custom Skills (`skills.json`)
Multi-step routines triggered by a phrase. Edit `skills.json` directly —
no code required:

```json
{
  "name": "morning routine",
  "triggers": ["good morning", "start my day"],
  "actions": [
    {"type": "speak", "text": "Good morning, sir!"},
    {"type": "open", "app": "Chrome"},
    {"type": "search", "query": "morning news"}
  ]
}
```
Action types: `speak`, `open`, `search`, `volume`, `url`.
Say "list skills" to hear what's defined, "reload skills" after editing the file.

### Plugins (`plugins/`)
Drop any `.py` file into `plugins/` to add new commands without touching the
core engine. Two examples are included:

- `calculator.py` — "what is 12 times 4" calculates the result
- `reminders.py` — "remind me to call mom" saves and lists reminders

Plugin contract:
```python
TRIGGERS = ["keyword1", "keyword2"]
def handle(text: str, ctx: dict) -> str | None:
    # Return a response string, or None to let Jarvis try other handlers
    ...
```

---

## Phase 4 — GUI, Email/Calendar, Screen Vision

### System Tray Mode
Run `python jarvis_tray.py` instead of `jarvis.py` to keep Jarvis running
quietly in the background. Right-click the tray icon for:
speak test, type a command, toggle wake-word listening, view memory summary,
reload skills, quit.

### Email & Calendar (Gmail + Google Calendar)
One-time setup:
1. Go to console.cloud.google.com and create a project
2. Enable Gmail API and Google Calendar API
3. Create OAuth credentials (Desktop app type) and download as `credentials.json`
4. Place `credentials.json` in the Jarvis folder
5. First voice command triggers a one-time browser authorization; token is cached after

| Say | Does |
|---|---|
| "Check my email" | Summarizes unread messages |
| "My schedule" / "Today's meetings" | Lists upcoming calendar events |

Until `credentials.json` is added, Jarvis tells you it's not configured instead
of crashing — everything else keeps working normally.

### Screen Vision
Jarvis can take a screenshot and describe it using Claude's vision capability.

| Say | Does |
|---|---|
| "What's on my screen?" | Describes the current screen |
| "What does this error mean?" | Explains visible error text |
| "Summarize this page" | Reads and summarizes a webpage on screen |

No extra setup — works as soon as `pyautogui` is installed.

---

## Configuration (`config.json`)

```json
{
  "wake_word": "hey jarvis",
  "wake_word_engine": "simple",
  "porcupine_access_key": "",
  "voice_rate": 175,
  "voice_volume": 0.9,
  "whisper_model": "base",
  "listen_duration": 6,
  "memory_max_turns": 40,
  "context_window": 20,
  "personality": "..."
}
```

- `whisper_model`: tiny (fastest) -> base -> small -> medium (most accurate)
- `memory_max_turns`: how many conversation turns are kept in `memory.json`
- `context_window`: how many recent turns are sent to Claude per request
- `personality`: edit this to change Jarvis's tone entirely

---

## Requirements

- Python 3.9+
- Anthropic API key (console.anthropic.com)
- FFmpeg (for Whisper voice recognition)
- Microphone
- Optional: Google Cloud OAuth credentials (email/calendar), Picovoice key (wake word)

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

---

## Extending Jarvis

Three ways, from easiest to most flexible:

1. Skills (`skills.json`) — no code, just JSON, good for routines
2. Plugins (`plugins/*.py`) — light Python, good for new logic (calculators, lookups, integrations)
3. Core edits (`jarvis.py`) — direct edits to `CommandHandler.handle()` for anything deeply integrated

Anything not matched by skills, plugins, or built-in commands is sent to
Claude AI automatically — so Jarvis always has a fallback answer.

---

## Roadmap status

- [x] Phase 1: Voice input (Whisper) + Claude AI + Voice output (pyttsx3)
- [x] Phase 2: App control, web search, file ops, system info
- [x] Phase 3: Wake word, persistent memory, custom skills, plugin system
- [x] Phase 4: Tray GUI, email/calendar integration, screen vision
- [ ] Phase 5 ideas: mobile companion app, multi-language support, local LLM fallback for offline use
