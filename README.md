# J.A.R.V.I.S — AI Laptop Assistant
### Powered by Claude AI · Fully operational on Windows 11

A voice-controlled AI assistant that lives on your laptop.
Say **"Hey Jarvis"** anytime — it wakes up, listens, speaks back,
remembers your conversations, controls your computer, generates images,
and can even be your personal mentor and friend.

---

## Quick Start (Windows 11)

```cmd
# 1. Install dependencies
pip install requests psutil pyttsx3 openai-whisper sounddevice soundfile numpy pyautogui pillow pystray google-auth google-auth-oauthlib google-api-python-client

# 2. Set your Anthropic API key (get one free at console.anthropic.com)
setx ANTHROPIC_API_KEY "sk-ant-your-key-here"

# 3. Close Command Prompt, open a new one, then run
python jarvis.py

# Optional: run silently in system tray instead
python jarvis_tray.py
```

> **First run only:** Jarvis downloads the Whisper voice model (~140 MB). Takes 2–3 minutes once, never again.

---

## File structure

```
jarvis/
├── jarvis.py            ← Main engine — run this
├── jarvis_tray.py       ← Background tray mode
├── image_gen.py         ← AI image generation
├── screen_vision.py     ← Screen reading with Claude vision
├── email_calendar.py    ← Gmail + Google Calendar
├── config.json          ← All settings (edit this to customise)
├── skills.json          ← Your custom voice routines
├── memory.json          ← Auto-created — conversation history
├── requirements.txt     ← All Python packages
└── plugins/
    ├── calculator.py    ← "what is 12 times 4"
    └── reminders.py     ← "remind me to call mom"
```

---

## Wake word

Say **"Hey Jarvis"** at any time — even while doing other things.

Jarvis responds: *"Hello sir, I'm Jarvis, your personal assistant at work. How may I help you?"*

After you speak your command it says *"I got you"* to confirm it heard you, then answers.

Also responds to: *"Ok Jarvis", "Hi Jarvis", "Yo Jarvis"*

---

## Everything Jarvis can do

### Conversation & AI
| Say | Does |
|---|---|
| Anything — any question | Claude AI answers naturally in spoken voice |
| "Remember that my name is Ayush" | Saves the fact permanently |
| "What do you remember?" | Recalls stored facts and history |
| "Who am I?" | Recalls your name |
| "Clear memory" | Wipes conversation history |

### Mentor / Friend Mode
Say **"mentor mode"** or **"be my mentor"** to switch Jarvis into a warm, conversational friend persona.

In mentor mode Jarvis:
- Talks back and forth without needing "Hey Jarvis" between each message
- Asks follow-up questions to understand your situation
- Validates your feelings before jumping to solutions
- Gives honest advice like a close friend would
- Keeps the conversation going naturally

Say **"exit mentor"** to return to normal assistant mode.

### Voice to Notepad (Dictation)
Say **"take notes"**, **"start dictation"**, **"open notepad"**, or **"write this down"**.

Jarvis opens a dictation session:
1. Speak anything — paragraphs, ideas, instructions
2. Claude automatically adds punctuation and fixes speech errors
3. Each chunk is confirmed with *"Got it."*
4. Say **"stop dictation"** when done
5. File saves automatically as `jarvis_note_YYYYMMDD_HHMMSS.txt` in your Documents
6. Opens in Notepad instantly

### App Control
| Say | Does |
|---|---|
| "Open Chrome" | Opens Chrome |
| "Open Notepad" | Opens Notepad |
| "Open Calculator" | Opens Calculator |
| "Open Spotify" | Opens Spotify (or web player) |
| "Open VS Code" | Opens Visual Studio Code |
| "Open File Explorer" | Opens Explorer |
| "Open Task Manager" | Opens Task Manager |
| "Open WhatsApp" | Opens WhatsApp |
| "Open Zoom / Teams / Discord" | Opens respective app |
| "Close Spotify" | Closes the running app |
| "Close Chrome" | Closes Chrome |

### Volume Controls
| Say | Does |
|---|---|
| "Volume up" | Increases volume |
| "Volume down" | Decreases volume |
| "Mute" | Mutes audio |
| "Unmute" | Unmutes audio |
| "Set volume to 60" | Sets exact volume level (0–100) |

### Brightness Controls
| Say | Does |
|---|---|
| "Brightness up" | Increases screen brightness |
| "Brightness down" | Decreases screen brightness |
| "Set brightness to 70" | Sets exact brightness level (0–100) |

### System Controls
| Say | Does |
|---|---|
| "Lock screen" | Locks the computer immediately |
| "Sleep" | Suspends the laptop |
| "Shutdown computer" | 10-second countdown then shuts down |
| "Restart computer" | 10-second countdown then restarts |
| "Take a screenshot" | Saves to ~/Pictures |

### System Info
| Say | Does |
|---|---|
| "What time is it?" | Current time |
| "What's today's date?" | Current date |
| "Battery status" | Battery % and charging state |
| "CPU performance" | CPU, RAM and disk usage |
| "Weather in Mumbai" | Live weather for any city |
| "System uptime" | How long the laptop has been on |

### Web & Search
| Say | Does |
|---|---|
| "Search Python tutorials" | Opens Google search |
| "YouTube lo-fi music" | Searches YouTube |
| "Open YouTube" | Opens youtube.com |
| "Open GitHub" | Opens github.com |
| "Open Gmail" | Opens Gmail |
| "Go to reddit.com" | Opens any website |

### Image Generation (AI)
| Say | Does |
|---|---|
| "Draw a dragon breathing fire" | Generates and opens the image |
| "Generate an image of a sunset" | AI image, saved to ~/Pictures/jarvis_images |
| "Paint a watercolor forest" | Watercolor style auto-detected |
| "Imagine a cyberpunk city" | Cyberpunk style auto-detected |
| "Show my images" | Lists recently generated images |
| "Open last image" | Opens most recent generated image |

Styles auto-detected from your words: photorealistic, anime, cartoon, oil painting, watercolor, digital art, sketch, fantasy, cyberpunk, minimalist.

Default backend: **Pollinations.ai** (free, no key needed). Optional: set `OPENAI_API_KEY` for DALL-E 3 quality.

### Screen Vision
| Say | Does |
|---|---|
| "What's on my screen?" | Jarvis describes what it sees |
| "What does this error mean?" | Explains visible error |
| "Summarize this page" | Reads and summarizes a webpage |

### Files
| Say | Does |
|---|---|
| "Create file report.txt" | Creates a new file |
| "Open folder Documents" | Opens folder in Explorer |
| "List files in Downloads" | Lists folder contents |

### Custom Skills
Multi-step routines defined in `skills.json` — no code needed:

```json
{
  "name": "morning routine",
  "triggers": ["good morning", "start my day"],
  "actions": [
    {"type": "speak", "text": "Good morning sir!"},
    {"type": "open", "app": "Chrome"},
    {"type": "search", "query": "morning news today"}
  ]
}
```

Built-in skills: **good morning**, **focus mode**, **goodnight**, **work setup**, **research mode**.

Say "list skills" to hear all defined skills. Say "reload skills" after editing the file.

### Plugins
Drop any `.py` file into the `plugins/` folder to add new commands:

```python
TRIGGERS = ["my trigger word"]
def handle(text: str, ctx: dict) -> str | None:
    return "My response"  # or None to fall through
```

Built-in plugins: **calculator** ("what is 15 times 8"), **reminders** ("remind me to email John").

### Shutdown Phrases
Any of these will close Jarvis gracefully with a spoken goodbye:
*goodbye, shutdown, turn off, bye jarvis, see you later, that's all, I'm done, stop jarvis, power off, exit*

---

## Configuration (`config.json`)

| Setting | Default | What it does |
|---|---|---|
| `wake_word` | `"hey jarvis"` | The phrase that wakes Jarvis up |
| `wake_word_engine` | `"simple"` | `"simple"` (Whisper-based) or `"porcupine"` (faster, needs free key) |
| `porcupine_access_key` | `""` | Key from console.picovoice.ai for Porcupine engine |
| `voice_rate` | `165` | Speaking speed (words per minute) |
| `voice_volume` | `1.0` | Volume 0.0 to 1.0 |
| `voice_name` | `""` | Preferred voice name e.g. `"zira"` or `"david"` |
| `whisper_model` | `"base"` | `tiny` (fast) → `base` → `small` → `medium` (accurate) |
| `listen_duration` | `6` | Seconds to record after wake word |
| `memory_max_turns` | `40` | Conversation turns saved to memory.json |
| `context_window` | `20` | Recent turns sent to Claude per request |
| `personality` | (long string) | Edit to change Jarvis's tone and behaviour |

---

## Optional Upgrades

### Email & Calendar (Gmail + Google Calendar)
1. Go to `console.cloud.google.com` → create a project
2. Enable **Gmail API** and **Google Calendar API**
3. Create OAuth credentials (Desktop app) → download as `credentials.json`
4. Place `credentials.json` in the Jarvis folder
5. First command triggers a one-time browser login — cached forever after

Then say: *"check my email"*, *"my schedule"*, *"today's meetings"*

### Accurate Wake Word (Porcupine)
Get a free key at `console.picovoice.ai`. In `config.json` set:
```json
"wake_word_engine": "porcupine",
"porcupine_access_key": "your-key-here"
```
Lower CPU usage, faster response, more accurate detection.

### Better Image Generation (DALL-E 3)
```cmd
setx OPENAI_API_KEY "sk-your-openai-key"
```
Jarvis automatically upgrades to DALL-E 3 quality images.

### Hugging Face Images (Free)
```cmd
setx HF_TOKEN "hf_your_token"
```

---

## Troubleshooting

**Jarvis types but doesn't speak**
```cmd
python -c "import pyttsx3; e=pyttsx3.init(); e.say('hello'); e.runAndWait()"
```
If no voice: `pip uninstall pyttsx3 -y && pip install pyttsx3`
Also check: speakers plugged in, not muted, correct output device selected in Windows sound settings.

**"connectivity issues" or "'content' error"**
```cmd
echo %ANTHROPIC_API_KEY%
```
If blank: `setx ANTHROPIC_API_KEY "your-key"` in a new Command Prompt.
If key shows: check billing at `console.anthropic.com` — add $5 credits.

**Wake word not detecting**
Make sure your microphone is not muted and Windows has mic permission:
Settings → Privacy → Microphone → allow desktop apps.

**FP16 warning (harmless)**
`UserWarning: FP16 is not supported on CPU; using FP32 instead` — safe to ignore. Whisper automatically uses the correct mode for your CPU.

**WinError 32 (file lock)**
Already fixed in the latest jarvis.py. Re-download if you still see it.

---

## Saving changes with Git

Every time you edit a file, run these 3 commands to back it up to GitHub:

```cmd
git add .
git commit -m "describe what you changed"
git push
```

To restore Jarvis on a new laptop:
```cmd
git clone https://github.com/YourUsername/jarvis.git
cd jarvis
pip install -r requirements.txt
python jarvis.py
```

---

## What's built

- [x] Phase 1: Voice input (Whisper) + Claude AI brain + Voice output (pyttsx3 / PowerShell)
- [x] Phase 2: App open/close, web search, file ops, system info, weather
- [x] Phase 3: Wake word ("Hey Jarvis"), persistent memory, custom skills, plugin system
- [x] Phase 4: System tray GUI, Gmail/Calendar, screen vision, AI image generation
- [x] Phase 5: Natural spoken greeting, "I got you" confirmation, voice dictation to Notepad, mentor/friend mode, full volume/brightness/shutdown controls
- [ ] Future ideas: mobile app, multi-language, offline local LLM, Spotify control
