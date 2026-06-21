"""
JARVIS - Just A Rather Very Intelligent System
Voice-controlled AI assistant for laptop automation
Powered by Claude AI

Phase 3 additions:
  - Wake word detection ("Hey Jarvis") — always-on background listener
  - Persistent conversation memory (saved to disk, survives restarts)
  - Custom skills system (define your own commands in skills.json)
  - Plugin architecture (drop .py files into plugins/ folder)
  - Configurable via config.json
  - Multi-turn context awareness
"""

import os
import sys
import json
import time
import queue
import struct
import threading
import subprocess
import platform
import webbrowser
import datetime
import psutil
import requests
import importlib.util
from pathlib import Path
from collections import deque

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
CONFIG_FILE   = BASE_DIR / "config.json"
SKILLS_FILE   = BASE_DIR / "skills.json"
MEMORY_FILE   = BASE_DIR / "memory.json"
PLUGINS_DIR   = BASE_DIR / "plugins"
PLUGINS_DIR.mkdir(exist_ok=True)

# ─── Config ──────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "wake_word": "hey jarvis",
    "wake_word_engine": "simple",       # "simple" (keyword match) or "porcupine" (accurate)
    "porcupine_access_key": "",         # Only needed if engine = "porcupine"
    "voice_rate": 175,
    "voice_volume": 0.9,
    "whisper_model": "base",            # tiny / base / small / medium
    "listen_duration": 6,              # seconds to record after wake word
    "memory_max_turns": 40,            # turns to keep in long-term memory
    "context_window": 20,              # turns sent to Claude per request
    "personality": "You are Jarvis, a brilliant AI laptop assistant inspired by Iron Man. "
                   "You are helpful, direct, and subtly witty. Keep responses concise (1-3 sentences) "
                   "unless detail is explicitly needed. Address the user as 'sir' occasionally."
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        cfg = {**DEFAULT_CONFIG, **saved}
    else:
        cfg = DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg

CONFIG = load_config()

# ─── Persistent Memory ───────────────────────────────────────────────────────
class Memory:
    """
    Saves conversation history to disk so Jarvis remembers across restarts.
    Also tracks named facts the user tells Jarvis ("remember that my name is Arjun").
    """
    def __init__(self):
        self.turns: deque = deque(maxlen=CONFIG["memory_max_turns"])
        self.facts: dict  = {}
        self._load()

    def _load(self):
        if MEMORY_FILE.exists():
            try:
                data = json.loads(MEMORY_FILE.read_text())
                for t in data.get("turns", []):
                    self.turns.append(t)
                self.facts = data.get("facts", {})
                print(f"📂 Memory loaded: {len(self.turns)} turns, {len(self.facts)} facts.")
            except Exception:
                pass

    def save(self):
        data = {"turns": list(self.turns), "facts": self.facts}
        MEMORY_FILE.write_text(json.dumps(data, indent=2))

    def add_turn(self, role: str, content: str):
        self.turns.append({"role": role, "content": content})
        self.save()

    def remember_fact(self, key: str, value: str):
        self.facts[key] = value
        self.save()

    def recall_fact(self, key: str) -> str:
        return self.facts.get(key, "")

    def get_context(self) -> list:
        """Return last N turns for Claude context."""
        return list(self.turns)[-CONFIG["context_window"]:]

    def clear(self):
        self.turns.clear()
        self.facts.clear()
        self.save()
        return "Memory wiped. Starting fresh, sir."

    def summarize(self) -> str:
        turns = len(self.turns)
        facts = len(self.facts)
        if not turns and not facts:
            return "Memory is empty."
        parts = []
        if turns:
            parts.append(f"{turns} conversation turns stored")
        if facts:
            flist = ", ".join(f"{k}: {v}" for k, v in list(self.facts.items())[:5])
            parts.append(f"known facts: {flist}")
        return "I remember " + "; ".join(parts) + "."

# ─── Custom Skills ────────────────────────────────────────────────────────────
class SkillsManager:
    """
    Loads user-defined command shortcuts from skills.json.
    Format:
    {
      "skills": [
        {
          "name": "morning routine",
          "triggers": ["good morning", "start my day"],
          "actions": [
            {"type": "speak", "text": "Good morning! Starting your routine."},
            {"type": "open",  "app": "Spotify"},
            {"type": "open",  "app": "Chrome"},
            {"type": "search","query": "morning news"}
          ]
        }
      ]
    }
    """
    def __init__(self):
        self.skills = []
        self._load()

    def _load(self):
        if not SKILLS_FILE.exists():
            # Create a sample skills file
            sample = {
                "skills": [
                    {
                        "name": "morning routine",
                        "triggers": ["good morning", "start my day", "morning routine"],
                        "actions": [
                            {"type": "speak", "text": "Good morning, sir! Starting your daily routine."},
                            {"type": "open",  "app": "Chrome"},
                            {"type": "search","query": "morning news today"}
                        ]
                    },
                    {
                        "name": "focus mode",
                        "triggers": ["focus mode", "start focus", "i need to focus"],
                        "actions": [
                            {"type": "speak", "text": "Enabling focus mode. Minimizing distractions."},
                            {"type": "volume","direction": "down"},
                            {"type": "speak", "text": "All set. Focus mode active."}
                        ]
                    },
                    {
                        "name": "goodnight",
                        "triggers": ["goodnight", "good night", "i'm going to sleep"],
                        "actions": [
                            {"type": "speak", "text": "Goodnight, sir. Sleep well."},
                            {"type": "volume","direction": "mute"}
                        ]
                    }
                ]
            }
            SKILLS_FILE.write_text(json.dumps(sample, indent=2))
            self.skills = sample["skills"]
            print(f"📋 Created sample skills.json with {len(self.skills)} skills.")
        else:
            try:
                data = json.loads(SKILLS_FILE.read_text())
                self.skills = data.get("skills", [])
                print(f"📋 Loaded {len(self.skills)} custom skills.")
            except Exception as e:
                print(f"[Skills] Error loading skills.json: {e}")

    def match(self, text: str) -> list | None:
        """Return list of actions if text matches a skill trigger, else None."""
        t = text.lower().strip()
        for skill in self.skills:
            for trigger in skill.get("triggers", []):
                if trigger.lower() in t:
                    return skill["actions"]
        return None

    def list_skills(self) -> str:
        if not self.skills:
            return "No custom skills defined. Edit skills.json to add some."
        names = [s["name"] for s in self.skills]
        return "Custom skills: " + ", ".join(names) + "."

    def reload(self):
        self.skills = []
        self._load()
        return f"Skills reloaded. {len(self.skills)} skills active."

# ─── Plugin System ────────────────────────────────────────────────────────────
class PluginManager:
    """
    Loads Python plugins from the plugins/ directory.
    Each plugin must define:
        TRIGGERS = ["keyword1", "keyword2"]
        def handle(text: str, jarvis_context: dict) -> str: ...
    """
    def __init__(self):
        self.plugins = []
        self._load()

    def _load(self):
        if not any(PLUGINS_DIR.glob("*.py")):
            self._create_example_plugin()

        for f in sorted(PLUGINS_DIR.glob("*.py")):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f.stem, f)
                mod  = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                triggers = getattr(mod, "TRIGGERS", [])
                handler  = getattr(mod, "handle", None)
                if triggers and handler:
                    self.plugins.append({"name": f.stem, "triggers": triggers, "handle": handler})
                    print(f"🔌 Plugin loaded: {f.stem} ({len(triggers)} triggers)")
            except Exception as e:
                print(f"[Plugin] Failed to load {f.name}: {e}")

    def _create_example_plugin(self):
        example = '''"""
Example Jarvis plugin: Calculator
Drop any .py file into the plugins/ folder to extend Jarvis.
"""
import re

TRIGGERS = ["calculate", "what is", "how much is", "compute"]

def handle(text: str, ctx: dict) -> str:
    """Try to evaluate a math expression from the command."""
    expr = re.sub(r"[^0-9+\\-*/().% ]", "", text.lower()
                  .replace("calculate", "")
                  .replace("what is", "")
                  .replace("how much is", "")
                  .replace("compute", "")
                  .replace("x", "*")
                  .replace("times", "*")
                  .replace("divided by", "/")
                  .replace("plus", "+")
                  .replace("minus", "-")).strip()
    if not expr:
        return None  # Return None to fall through to AI
    try:
        result = eval(expr, {"__builtins__": {}})
        return f"The result is {result}."
    except Exception:
        return None  # Let Claude handle it
'''
        (PLUGINS_DIR / "calculator.py").write_text(example)
        print("🔌 Created example plugin: plugins/calculator.py")

    def match(self, text: str, ctx: dict) -> str | None:
        t = text.lower()
        for plugin in self.plugins:
            if any(trigger in t for trigger in plugin["triggers"]):
                try:
                    result = plugin["handle"](text, ctx)
                    if result:
                        return result
                except Exception as e:
                    print(f"[Plugin:{plugin['name']}] Error: {e}")
        return None

# ─── Wake Word Engine ─────────────────────────────────────────────────────────
class WakeWordDetector:
    """
    Background thread that listens for "Hey Jarvis" continuously.
    Two engines:
      - simple:     VAD + whisper transcription (no extra API key, slightly slower)
      - porcupine:  Picovoice Porcupine (accurate, fast, needs free access key)
    """
    def __init__(self, callback, config: dict):
        self.callback   = callback  # called when wake word detected
        self.config     = config
        self.engine     = config.get("wake_word_engine", "simple")
        self.wake_word  = config.get("wake_word", "hey jarvis").lower()
        self._running   = False
        self._thread    = None
        self._porcupine = None
        self._paused    = threading.Event()
        self._paused.set()  # not paused by default

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"👂 Wake word detector started — say \"{self.wake_word.title()}\" to activate.")

    def stop(self):
        self._running = False

    def pause(self):
        """Pause detection while Jarvis is speaking or processing."""
        self._paused.clear()

    def resume(self):
        """Resume detection."""
        self._paused.set()

    def _run(self):
        if self.engine == "porcupine":
            self._run_porcupine()
        else:
            self._run_simple()

    def _run_simple(self):
        """
        Simple engine: record 3-second chunks, transcribe with Whisper,
        check for wake phrase. Low CPU usage between chunks.
        """
        try:
            import whisper
            import sounddevice as sd
            import soundfile as sf
            import numpy as np
            import tempfile

            model = getattr(listen_microphone, "_model", None)
            if model is None:
                print("[WakeWord] Whisper model not loaded — wake word disabled.")
                return

            samplerate = 16000
            chunk_secs = 3

            while self._running:
                self._paused.wait()  # block while paused

                audio = sd.rec(int(chunk_secs * samplerate), samplerate=samplerate,
                               channels=1, dtype='float32')
                sd.wait()

                if not self._paused.is_set():
                    continue

                audio_flat = audio.flatten()
                # Quick energy check to skip silence
                if np.abs(audio_flat).mean() < 0.002:
                    continue

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    sf.write(f.name, audio_flat, samplerate)
                    try:
                        result = model.transcribe(f.name, language="en",
                                                   condition_on_previous_text=False)
                        transcript = result["text"].lower().strip()
                    except Exception:
                        transcript = ""
                    finally:
                        os.unlink(f.name)

                if self.wake_word in transcript or \
                   "jarvis" in transcript and ("hey" in transcript or "ok" in transcript or "yo" in transcript):
                    if self._paused.is_set():
                        self.callback()

        except Exception as e:
            print(f"[WakeWord/simple] Error: {e}")

    def _run_porcupine(self):
        """Picovoice Porcupine — accurate, low CPU, needs free access key."""
        try:
            import pvporcupine
            import sounddevice as sd

            access_key = self.config.get("porcupine_access_key", "")
            if not access_key:
                print("[WakeWord] Porcupine access key missing — falling back to simple engine.")
                self._run_simple()
                return

            porcupine = pvporcupine.create(
                access_key=access_key,
                keywords=["jarvis"]
            )
            self._porcupine = porcupine

            q = queue.Queue()

            def audio_callback(indata, frames, time_, status):
                q.put(bytes(indata))

            with sd.RawInputStream(samplerate=porcupine.sample_rate,
                                   blocksize=porcupine.frame_length,
                                   dtype='int16', channels=1,
                                   callback=audio_callback):
                while self._running:
                    self._paused.wait()
                    pcm = q.get()
                    pcm_unpacked = struct.unpack_from("h" * porcupine.frame_length, pcm)
                    result = porcupine.process(pcm_unpacked)
                    if result >= 0 and self._paused.is_set():
                        self.callback()

            porcupine.delete()

        except ImportError:
            print("[WakeWord] pvporcupine not installed — falling back to simple engine.")
            self._run_simple()
        except Exception as e:
            print(f"[WakeWord/porcupine] Error: {e}. Falling back to simple engine.")
            self._run_simple()

# ─── Voice Input ─────────────────────────────────────────────────────────────
def listen_microphone(duration: int = None) -> str | None:
    """Record from mic and transcribe with Whisper."""
    dur = duration or CONFIG["listen_duration"]
    try:
        import sounddevice as sd
        import soundfile as sf
        import numpy as np
        import tempfile

        model = listen_microphone._model
        print(f"\n🎤 Listening... ({dur}s)")
        samplerate = 16000
        audio = sd.rec(int(dur * samplerate), samplerate=samplerate,
                       channels=1, dtype='float32')
        sd.wait()
        audio = audio.flatten()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, samplerate)
            result = model.transcribe(f.name, language="en")
            text = result["text"].strip()
            os.unlink(f.name)

        if text:
            print(f"👤 You said: {text}")
        return text or None

    except Exception as e:
        print(f"[Voice error] {e}")
        return None


def load_whisper_model() -> bool:
    try:
        import whisper
        size = CONFIG.get("whisper_model", "base")
        print(f"🔄 Loading Whisper '{size}' model...")
        listen_microphone._model = whisper.load_model(size)
        print("✅ Whisper ready.")
        return True
    except ImportError:
        print("⚠️  Whisper not installed. Run: pip install openai-whisper sounddevice soundfile")
        return False

# ─── Voice Output ─────────────────────────────────────────────────────────────
_tts_engine = None

def _get_tts_engine():
    global _tts_engine
    if _tts_engine is None:
        try:
            import pyttsx3
            _tts_engine = pyttsx3.init()
            _tts_engine.setProperty('rate', CONFIG["voice_rate"])
            _tts_engine.setProperty('volume', CONFIG["voice_volume"])
            voices = _tts_engine.getProperty('voices')
            for v in voices:
                if 'english' in v.name.lower() or 'david' in v.name.lower():
                    _tts_engine.setProperty('voice', v.id)
                    break
        except Exception:
            pass
    return _tts_engine

def speak(text: str, wake_detector: WakeWordDetector = None):
    """Speak text, pausing wake word detection while doing so."""
    print(f"\n🤖 Jarvis: {text}")
    if wake_detector:
        wake_detector.pause()
    try:
        engine = _get_tts_engine()
        if engine:
            engine.say(text)
            engine.runAndWait()
        else:
            raise RuntimeError("No TTS engine")
    except Exception:
        os_name = platform.system()
        try:
            if os_name == "Darwin":
                subprocess.run(["say", text], check=False)
            elif os_name == "Linux":
                subprocess.run(["espeak", "-s", "175", text], check=False)
            elif os_name == "Windows":
                subprocess.run(
                    ["powershell", "-Command",
                     f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"],
                    check=False
                )
        except Exception:
            pass
    finally:
        if wake_detector:
            wake_detector.resume()

# ─── Claude AI Brain ──────────────────────────────────────────────────────────
class JarvisAI:
    def __init__(self, api_key: str, memory: Memory):
        self.api_key = api_key
        self.memory  = memory

    def chat(self, user_message: str, extra_context: str = "") -> str:
        """Send message to Claude with full persistent memory context."""
        # Build system prompt with known facts injected
        facts_str = ""
        if self.memory.facts:
            facts_str = "\n\nKnown facts about the user:\n" + \
                        "\n".join(f"- {k}: {v}" for k, v in self.memory.facts.items())

        system = CONFIG["personality"] + facts_str
        if extra_context:
            system += f"\n\nAdditional context: {extra_context}"

        self.memory.add_turn("user", user_message)
        context = self.memory.get_context()

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 512,
                    "system": system,
                    "messages": context,
                },
                timeout=15,
            )
            data = response.json()
            reply = data["content"][0]["text"]
            self.memory.add_turn("assistant", reply)
            return reply
        except Exception as e:
            return f"I seem to be having connectivity issues, sir. {e}"

# ─── Command Handler ──────────────────────────────────────────────────────────
class CommandHandler:
    def __init__(self, jarvis_ai: JarvisAI, memory: Memory,
                 skills: SkillsManager, plugins: PluginManager,
                 wake_detector: WakeWordDetector = None):
        self.ai           = jarvis_ai
        self.memory       = memory
        self.skills       = skills
        self.plugins      = plugins
        self.wake         = wake_detector
        self.os_name      = platform.system()

        # ── Phase 4 modules (optional — degrade gracefully if unavailable) ──
        self.vision    = None
        self.email_cal = None
        self.image_gen = None
        try:
            from screen_vision import ScreenVision
            self.vision = ScreenVision(jarvis_ai.api_key)
        except Exception as e:
            print(f"[Phase4] Screen vision unavailable: {e}")
        try:
            from email_calendar import EmailCalendarSkill
            self.email_cal = EmailCalendarSkill()
        except Exception as e:
            print(f"[Phase4] Email/calendar unavailable: {e}")
        try:
            from image_gen import ImageGenerator
            self.image_gen = ImageGenerator(jarvis_ai.api_key, {
                "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
                "hf_token":       os.environ.get("HF_TOKEN", ""),
            })
            print(f"[ImageGen] Ready — backend: {self.image_gen.backend.name}")
        except Exception as e:
            print(f"[ImageGen] Unavailable: {e}")

    def handle(self, text: str) -> str:
        t = text.lower().strip()

        # ── Memory commands ──────────────────────────────────────────────
        if t.startswith("remember that ") or t.startswith("remember "):
            return self._remember(text)

        if any(k in t for k in ["what do you remember", "your memory", "show memory"]):
            return self.memory.summarize()

        if any(k in t for k in ["forget everything", "clear memory", "wipe memory", "reset memory"]):
            return self.memory.clear()

        if any(k in t for k in ["who am i", "what's my name", "do you know my name"]):
            name = self.memory.recall_fact("name")
            return f"You're {name}, sir." if name else "I don't know your name yet. Tell me and I'll remember."

        # ── Skills ───────────────────────────────────────────────────────
        actions = self.skills.match(t)
        if actions:
            return self._run_skill_actions(actions)

        if any(k in t for k in ["list skills", "show skills", "what skills"]):
            return self.skills.list_skills()

        if any(k in t for k in ["reload skills", "refresh skills"]):
            return self.skills.reload()

        # ── Plugins ──────────────────────────────────────────────────────
        ctx = {"os": self.os_name, "memory": self.memory, "config": CONFIG}
        plugin_result = self.plugins.match(text, ctx)
        if plugin_result:
            return plugin_result

        # ── System info ──────────────────────────────────────────────────
        if any(k in t for k in ["time", "clock", "what time"]):
            return "It's " + datetime.datetime.now().strftime("%I:%M %p") + "."

        if any(k in t for k in ["date", "today is", "what day", "what's the date"]):
            return "Today is " + datetime.datetime.now().strftime("%A, %B %d, %Y") + "."

        if any(k in t for k in ["battery", "charge level"]):
            return self._battery()

        if any(k in t for k in ["cpu", "ram", "memory usage", "system performance", "processor"]):
            return self._system_stats()

        if "weather" in t:
            return self._weather(t)

        if any(k in t for k in ["uptime", "how long"]) and "running" in t:
            return self._uptime()

        # ── App control ──────────────────────────────────────────────────
        if t.startswith("open "):
            return self._open_app(text[5:].strip())

        if t.startswith("close ") or t.startswith("quit ") or t.startswith("kill "):
            return self._close_app(text.split(" ", 1)[1].strip())

        if any(k in t for k in ["volume up", "increase volume", "louder"]):
            return self._volume("up")

        if any(k in t for k in ["volume down", "decrease volume", "quieter"]):
            return self._volume("down")

        if any(k in t for k in ["mute", "silence audio"]):
            return self._volume("mute")

        if any(k in t for k in ["screenshot", "capture screen", "take a screenshot"]):
            return self._screenshot()

        if any(k in t for k in ["lock screen", "lock my screen", "lock computer"]):
            return self._lock_screen()

        if any(k in t for k in ["sleep", "hibernate", "suspend"]):
            return self._sleep()

        # ── Web ──────────────────────────────────────────────────────────
        if t.startswith("search ") or t.startswith("google "):
            return self._web_search(t.split(" ", 1)[1])

        if t.startswith("youtube ") or "play on youtube" in t:
            query = t.replace("play on youtube", "").replace("youtube", "").strip()
            return self._youtube(query)

        if "open youtube" in t:
            webbrowser.open("https://www.youtube.com")
            return "Opening YouTube."

        if "open github" in t:
            webbrowser.open("https://github.com")
            return "Opening GitHub."

        if "open gmail" in t:
            webbrowser.open("https://mail.google.com")
            return "Opening Gmail."

        if t.startswith("go to ") or t.startswith("visit "):
            site = t.split(" ", 2)[-1]
            if not site.startswith("http"):
                site = "https://" + site
            webbrowser.open(site)
            return f"Opening {site}."

        # ── Files ─────────────────────────────────────────────────────────
        if t.startswith("create file "):
            return self._create_file(text[12:].strip())

        if t.startswith("open file ") or t.startswith("open folder "):
            return self._open_path(text.split(" ", 2)[-1].strip())

        if t.startswith("list files") or t.startswith("show files"):
            folder = t.split("in ")[-1] if " in " in t else "."
            return self._list_files(folder)

        # ── Jarvis control ────────────────────────────────────────────────
        if any(k in t for k in ["help", "what can you do", "commands", "capabilities"]):
            return self._help()

        if any(k in t for k in ["stop", "goodbye", "bye jarvis", "shut down", "exit", "quit jarvis"]):
            return "SHUTDOWN"

        # ── Phase 4: Screen vision ─────────────────────────────────────────
        if self.vision:
            from screen_vision import route_vision_command
            vision_result = route_vision_command(text, self.vision)
            if vision_result:
                return vision_result

        # ── Phase 4: Email & Calendar ────────────────────────────────────
        if self.email_cal:
            ec_result = self.email_cal.handle(text)
            if ec_result:
                return ec_result

        # ── Image generation ─────────────────────────────────────────────
        if self.image_gen:
            from image_gen import route_image_command
            img_result = route_image_command(text, self.image_gen,
                                             speak_fn=lambda msg: speak(msg, self.wake))
            if img_result:
                return img_result

        # ── Default: Claude AI (with memory context) ──────────────────────
        return self.ai.chat(text)

    # ── Memory ───────────────────────────────────────────────────────────────
    def _remember(self, text: str) -> str:
        """Parse "remember that my name is Arjun" → saves name=Arjun."""
        t = text.lower().replace("remember that ", "").replace("remember ", "")
        # Try to parse "X is Y" / "my X is Y"
        import re
        m = re.match(r"(?:my\s+)?(.+?)\s+is\s+(.+)", t)
        if m:
            key   = m.group(1).strip()
            value = m.group(2).strip()
            self.memory.remember_fact(key, value)
            return f"Got it, I'll remember that your {key} is {value}."
        else:
            self.memory.remember_fact(t, t)
            return f"Noted: {t}."

    # ── Skill actions ─────────────────────────────────────────────────────────
    def _run_skill_actions(self, actions: list) -> str:
        results = []
        for action in actions:
            atype = action.get("type", "")
            if atype == "speak":
                results.append(action.get("text", ""))
            elif atype == "open":
                results.append(self._open_app(action.get("app", "")))
            elif atype == "search":
                results.append(self._web_search(action.get("query", "")))
            elif atype == "volume":
                results.append(self._volume(action.get("direction", "up")))
            elif atype == "url":
                webbrowser.open(action.get("url", ""))
                results.append(f"Opened {action.get('url', '')}.")
            elif atype == "say":
                msg = action.get("text", "")
                speak(msg, self.wake)
        # Return first speak action text, run the rest silently
        spoken = [r for r in results if r]
        return spoken[0] if spoken else "Skill executed."

    # ── System ────────────────────────────────────────────────────────────────
    def _battery(self) -> str:
        try:
            b = psutil.sensors_battery()
            if b:
                status = "charging" if b.power_plugged else "on battery"
                mins   = int(b.secsleft / 60) if b.secsleft > 0 else None
                time_  = f", about {mins} minutes remaining" if mins else ""
                return f"Battery at {b.percent:.0f}%, {status}{time_}."
            return "No battery detected — desktop system."
        except Exception:
            return "Couldn't read battery status."

    def _system_stats(self) -> str:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return (f"CPU at {cpu}%. "
                f"RAM: {ram.used/1e9:.1f}/{ram.total/1e9:.1f} GB ({ram.percent}%). "
                f"Disk: {disk.used/1e9:.0f}/{disk.total/1e9:.0f} GB used.")

    def _uptime(self) -> str:
        boot = datetime.datetime.fromtimestamp(psutil.boot_time())
        delta = datetime.datetime.now() - boot
        h, m = divmod(int(delta.total_seconds()), 3600)
        m //= 60
        return f"System has been running for {h} hours and {m} minutes."

    def _weather(self, text: str) -> str:
        city = "auto"
        words = text.split()
        for i, w in enumerate(words):
            if w in ("in", "for", "at") and i + 1 < len(words):
                city = "+".join(words[i+1:])
                break
        try:
            r = requests.get(f"https://wttr.in/{city}?format=3", timeout=5)
            return r.text.strip()
        except Exception:
            return "Couldn't fetch weather right now."

    def _open_app(self, app: str) -> str:
        app_lower = app.lower()
        try:
            if self.os_name == "Darwin":
                subprocess.Popen(["open", "-a", app])
            elif self.os_name == "Linux":
                subprocess.Popen([app_lower])
            elif self.os_name == "Windows":
                os.startfile(app)
            return f"Opening {app}."
        except Exception:
            web_apps = {
                "spotify":  "https://open.spotify.com",
                "gmail":    "https://mail.google.com",
                "maps":     "https://maps.google.com",
                "calendar": "https://calendar.google.com",
                "notion":   "https://www.notion.so",
                "slack":    "https://app.slack.com",
            }
            for k, url in web_apps.items():
                if k in app_lower:
                    webbrowser.open(url)
                    return f"Opening {app} in browser."
            return f"Couldn't find {app}. Make sure it's installed."

    def _close_app(self, app: str) -> str:
        killed = []
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if app.lower() in proc.info['name'].lower():
                    proc.terminate()
                    killed.append(proc.info['name'])
            except Exception:
                pass
        if killed:
            return f"Closed {', '.join(set(killed))}."
        return f"No running process found matching '{app}'."

    def _volume(self, direction: str) -> str:
        try:
            if self.os_name == "Darwin":
                cmds = {
                    "up":   "set volume output volume (output volume of (get volume settings) + 10)",
                    "down": "set volume output volume (output volume of (get volume settings) - 10)",
                    "mute": "set volume with output muted"
                }
                subprocess.run(["osascript", "-e", cmds[direction]])
            elif self.os_name == "Linux":
                cmds = {"up": "10%+", "down": "10%-", "mute": "toggle"}
                subprocess.run(["amixer", "-q", "sset", "Master", cmds[direction]])
            elif self.os_name == "Windows":
                steps = {"up": 2, "down": -2, "mute": 0}
                for _ in range(abs(steps.get(direction, 0))):
                    key = 0xAF if steps[direction] > 0 else 0xAE
                    subprocess.run(["nircmd.exe", "changesysvolume",
                                    str(3000 * steps.get(direction, 0))])
            return {"up": "Volume up.", "down": "Volume down.", "mute": "Muted."}.get(direction, "Done.")
        except Exception:
            return "Volume control unavailable on this system."

    def _screenshot(self) -> str:
        try:
            import pyautogui
            ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = str(Path.home() / "Pictures" / f"jarvis_screenshot_{ts}.png")
            Path(fname).parent.mkdir(exist_ok=True)
            pyautogui.screenshot(fname)
            return f"Screenshot saved to {fname}."
        except ImportError:
            return "Install pyautogui for screenshots: pip install pyautogui"
        except Exception as e:
            return f"Screenshot failed: {e}"

    def _lock_screen(self) -> str:
        try:
            if self.os_name == "Darwin":
                subprocess.run(["pmset", "displaysleepnow"])
            elif self.os_name == "Linux":
                subprocess.run(["loginctl", "lock-session"])
            elif self.os_name == "Windows":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
            return "Screen locked."
        except Exception:
            return "Couldn't lock screen."

    def _sleep(self) -> str:
        speak("Going to sleep. Goodnight, sir.", self.wake)
        try:
            if self.os_name == "Darwin":
                subprocess.run(["pmset", "sleepnow"])
            elif self.os_name == "Linux":
                subprocess.run(["systemctl", "suspend"])
            elif self.os_name == "Windows":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        except Exception:
            pass
        return ""

    def _web_search(self, query: str) -> str:
        url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
        webbrowser.open(url)
        return f"Searching Google for: {query}"

    def _youtube(self, query: str) -> str:
        url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
        webbrowser.open(url)
        return f"Searching YouTube for: {query}"

    def _create_file(self, name: str) -> str:
        try:
            path = Path.home() / name
            path.touch()
            return f"Created file: {path}"
        except Exception as e:
            return f"Couldn't create file: {e}"

    def _open_path(self, path_str: str) -> str:
        path = Path(path_str).expanduser()
        try:
            if self.os_name == "Darwin":
                subprocess.run(["open", str(path)])
            elif self.os_name == "Linux":
                subprocess.run(["xdg-open", str(path)])
            elif self.os_name == "Windows":
                os.startfile(str(path))
            return f"Opened {path}."
        except Exception:
            return f"Couldn't open {path}."

    def _list_files(self, folder: str) -> str:
        try:
            p = Path(folder).expanduser()
            files = [f.name for f in sorted(p.iterdir())][:12]
            return f"Files in {folder}: {', '.join(files)}."
        except Exception:
            return f"Couldn't list files in {folder}."

    def _help(self) -> str:
        extras = []
        if self.vision:
            extras.append("look at your screen")
        if self.email_cal and self.email_cal.available:
            extras.append("check email or your calendar")
        if self.image_gen:
            extras.append("generate images from voice descriptions")
        extra_str = (" I can also " + ", ".join(extras) + ".") if extras else ""

        return (
            "I remember our conversations across restarts. "
            "Tell me facts with 'remember that my name is X'. "
            "Custom skills run multi-step routines — say 'good morning' or 'focus mode'. "
            "Plugins in the plugins folder extend me automatically. "
            "Say 'Hey Jarvis' anytime to activate me — no button needed. "
            "I can open apps, control volume, search, and check system stats."
            + extra_str
            + " For images, say 'draw a sunset' or 'generate an image of a dragon'."
        )

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("""
╔══════════════════════════════════════════════╗
║   J.A.R.V.I.S  —  AI Laptop Assistant      ║
║   Phase 3: Wake Word + Memory + Skills      ║
╚══════════════════════════════════════════════╝
""")

    # API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key = input("🔑 Anthropic API key: ").strip()
        if not api_key:
            print("No API key. Exiting.")
            sys.exit(1)

    # Init subsystems
    memory  = Memory()
    skills  = SkillsManager()
    plugins = PluginManager()

    # Load Whisper
    voice_available = load_whisper_model()

    ai      = JarvisAI(api_key, memory)

    # Wake word detector (starts in background thread)
    wake_triggered = threading.Event()

    def on_wake():
        print("\n🔔 Wake word detected!")
        wake_triggered.set()

    wake = WakeWordDetector(on_wake, CONFIG)
    handler = CommandHandler(ai, memory, skills, plugins, wake)

    # Start wake word listener if voice is available
    if voice_available:
        wake.start()

    speak(f"Jarvis online. {memory.summarize()}", wake)

    print("\n" + "─"*48)
    print(f"Wake word: \"{CONFIG['wake_word'].title()}\"")
    print("Or type commands below. Type 'exit' to quit.")
    print("─"*48 + "\n")

    use_voice = voice_available

    while True:
        try:
            # Wait for wake word OR typed input
            user_input = None

            if use_voice:
                # Non-blocking: check if wake word fired or user typed
                print("💤 Waiting... (say wake word or type a command)")
                typed = [None]
                done  = threading.Event()

                def read_input():
                    try:
                        typed[0] = input().strip()
                    except EOFError:
                        pass
                    done.set()

                t = threading.Thread(target=read_input, daemon=True)
                t.start()

                # Wait for either typed input or wake word
                while not done.is_set() and not wake_triggered.is_set():
                    time.sleep(0.1)

                if wake_triggered.is_set():
                    wake_triggered.clear()
                    wake.pause()
                    speak("Yes, sir?", None)  # don't re-pause, already paused
                    user_input = listen_microphone()
                    wake.resume()
                    if not user_input:
                        speak("I didn't catch that.", wake)
                        continue
                else:
                    user_input = typed[0]
            else:
                user_input = input("⌨️  You: ").strip()

            if not user_input:
                continue

            # Meta-commands
            if user_input.lower() in ("voice", "toggle voice"):
                if voice_available:
                    use_voice = not use_voice
                    mode = "voice 🎤" if use_voice else "text ⌨️"
                    if use_voice:
                        wake.start() if not wake._running else None
                    speak(f"Switched to {mode} mode.", wake)
                else:
                    print("Voice unavailable — install openai-whisper first.")
                continue

            response = handler.handle(user_input)

            if response == "SHUTDOWN":
                speak("Shutting down. Goodbye, sir.", wake)
                wake.stop()
                memory.save()
                break

            if response:
                speak(response, wake)

        except KeyboardInterrupt:
            speak("Jarvis signing off.", wake)
            wake.stop()
            memory.save()
            break


if __name__ == "__main__":
    main()
