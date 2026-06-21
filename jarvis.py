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
    "wake_word_engine": "simple",
    "porcupine_access_key": "",
    "voice_rate": 165,
    "voice_volume": 1.0,
    "voice_name": "",
    "whisper_model": "base",
    "listen_duration": 6,
    "memory_max_turns": 40,
    "context_window": 20,
    "personality": (
        "You are Jarvis, a friendly AI assistant living inside this laptop. "
        "You are having a real spoken conversation — your words come out of speakers, not a screen. "
        "Rules you must always follow:\n"
        "- Talk like a real person, not like someone writing an essay.\n"
        "- Keep every reply SHORT — 1 to 3 sentences max unless the user asks for more detail.\n"
        "- Never use bullet points, numbered lists, asterisks, or headers — they sound terrible spoken aloud.\n"
        "- Never start with filler like 'Certainly!', 'Absolutely!', 'Great question!' — just answer.\n"
        "- Use contractions: you're, I'll, that's, don't, it's — formal words sound robotic when spoken.\n"
        "- For completed actions just say something brief like 'Done' or 'On it'.\n"
        "- Be warm and slightly witty — like a smart friend, not a corporate assistant.\n"
        "- Occasionally call the user 'sir' but don't overdo it.\n"
        "- If you don't know something, say so simply and move on.\n"
        "- For anything technical, give the short answer first and offer to explain more if they want."
    )
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
        Always-on wake word listener. Records 2-second chunks, transcribes
        with Whisper, fires callback when 'hey jarvis' (or similar) is heard.
        """
        try:
            import sounddevice as sd
            import soundfile as sf
            import numpy as np
            import tempfile

            model = getattr(listen_microphone, "_model", None)
            if model is None:
                print("[WakeWord] Whisper model not loaded — wake word disabled.")
                return

            samplerate = 16000
            chunk_secs = 2  # shorter chunks = faster response

            # All the ways someone might naturally say the wake word
            wake_variants = [
                "hey jarvis", "ok jarvis", "yo jarvis", "hi jarvis",
                "hello jarvis", "jarvis", "hey travis",  # common mishear
                "hey davis", "hey harris",               # common mishears
            ]

            print("[WakeWord] Listening for 'Hey Jarvis'...")

            while self._running:
                self._paused.wait()

                audio = sd.rec(int(chunk_secs * samplerate), samplerate=samplerate,
                               channels=1, dtype='float32')
                sd.wait()

                if not self._paused.is_set():
                    continue

                audio_flat = audio.flatten()
                # Skip near-silence (no point transcribing empty audio)
                if np.abs(audio_flat).mean() < 0.003:
                    continue

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp_path = f.name
                sf.write(tmp_path, audio_flat, samplerate)
                try:
                    result = model.transcribe(tmp_path, language="en",
                                               condition_on_previous_text=False,
                                               fp16=False)
                    transcript = result["text"].lower().strip()
                except Exception:
                    transcript = ""
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

                if not transcript:
                    continue

                # Check if any wake variant appears in the transcript
                detected = any(v in transcript for v in wake_variants)
                if detected and self._paused.is_set():
                    print(f"[WakeWord] Heard: '{transcript}' → waking up")
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
            tmp_path = f.name
        sf.write(tmp_path, audio, samplerate)
        try:
            result = model.transcribe(tmp_path, language="en")
            text = result["text"].strip()
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

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
_tts_lock = threading.Lock()
_tts_mode = None   # "pyttsx3" | "powershell" | "silent"

def _init_tts():
    """Detect which TTS method works on this machine and cache it."""
    global _tts_engine, _tts_mode

    if _tts_mode is not None:
        return  # already initialised

    # Try pyttsx3 first
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices') or []

        # On Windows, pick the best English voice (Zira=female, David/Mark=male)
        chosen = None
        prefer = CONFIG.get("voice_name", "").lower()
        for v in voices:
            n = v.name.lower()
            if prefer and prefer in n:
                chosen = v; break
            if any(x in n for x in ['zira', 'david', 'mark', 'hazel']):
                chosen = v; break
        if not chosen:
            for v in voices:
                if 'en' in v.id.lower() or 'english' in v.name.lower():
                    chosen = v; break
        if not chosen and voices:
            chosen = voices[0]
        if chosen:
            engine.setProperty('voice', chosen.id)

        engine.setProperty('rate', CONFIG.get("voice_rate", 165))
        engine.setProperty('volume', CONFIG.get("voice_volume", 1.0))

        _tts_engine = engine
        _tts_mode = "pyttsx3"
        print(f"🔊 TTS ready (pyttsx3) — voice: {chosen.name if chosen else 'default'}")
        return
    except Exception as e:
        print(f"[TTS] pyttsx3 failed: {e}")
        print("[TTS] Trying Windows built-in PowerShell voice...")

    # Fallback: Windows PowerShell built-in TTS (always available on Windows 10/11)
    if platform.system() == "Windows":
        try:
            test = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Add-Type -AssemblyName System.Speech; "
                 "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                 "$s.Volume = 100; $s.Rate = 1; $s.Speak('voice test')"],
                timeout=15, capture_output=True
            )
            if test.returncode == 0:
                _tts_mode = "powershell"
                print("🔊 TTS ready (Windows PowerShell built-in voice)")
                return
            else:
                print(f"[TTS] PowerShell TTS returned code {test.returncode}")
        except Exception as e:
            print(f"[TTS] PowerShell TTS also failed: {e}")

    _tts_mode = "silent"
    print("⚠️  TTS unavailable — Jarvis will type only.")


def _do_speak(text: str):
    """Actually speak text using the best available method."""
    global _tts_engine, _tts_mode

    if _tts_mode is None:
        _init_tts()

    if _tts_mode == "silent":
        return

    if _tts_mode == "pyttsx3":
        try:
            with _tts_lock:
                _tts_engine.say(text)
                _tts_engine.runAndWait()
            return
        except Exception as e:
            print(f"[TTS] pyttsx3 error mid-session: {e} — switching to PowerShell")
            _tts_engine = None
            _tts_mode = "powershell"

    if _tts_mode == "powershell":
        safe = text.replace("'", " ").replace('"', ' ').replace('\n', ' ')
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Add-Type -AssemblyName System.Speech; "
                 f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                 f"$s.Rate = 1; $s.Volume = 100; $s.Speak('{safe}')"],
                timeout=60, check=False
            )
        except Exception as e:
            print(f"[TTS] PowerShell speak failed: {e}")


def speak(text: str, wake_detector=None):
    """Print and speak a line. Pauses wake word detection while speaking."""
    if not text or not text.strip():
        return
    print(f"\n🤖 Jarvis: {text}")
    if wake_detector:
        wake_detector.pause()
    try:
        _do_speak(text)
    finally:
        if wake_detector:
            wake_detector.resume()


def run_tts_test():
    """Called once at startup to confirm audio is working."""
    _init_tts()
    if _tts_mode == "silent":
        print("\n⚠️  No working TTS found. Try: pip uninstall pyttsx3 && pip install pyttsx3")
    else:
        print(f"✅ Audio test passed — mode: {_tts_mode}")

# ─── Claude AI Brain ──────────────────────────────────────────────────────────
class JarvisAI:
    def __init__(self, api_key: str, memory: Memory):
        self.api_key      = api_key
        self.memory       = memory
        self.mentor_active = False

    MENTOR_PROMPT = (
        "You are Jarvis in mentor/friend mode — a warm, emotionally intelligent friend "
        "who also happens to be extremely knowledgeable. "
        "The user is talking to you like a close friend for advice, support, or to think something through. "
        "Rules for this mode:\n"
        "- Be warm, empathetic, and conversational — like a best friend, not a consultant.\n"
        "- Ask follow-up questions to understand their situation better.\n"
        "- Don't lecture or give long essays — have a back-and-forth conversation.\n"
        "- Validate their feelings before jumping to solutions.\n"
        "- Keep replies short (2-4 sentences) — this is a spoken conversation.\n"
        "- Use their name if you know it. No bullet points, no lists, no markdown.\n"
        "- If they seem stressed, acknowledge it first before helping.\n"
        "- Be honest even if it's not what they want to hear — a good friend tells the truth."
    )

    def chat(self, user_message: str, extra_context: str = "") -> str:
        """Send message to Claude with full persistent memory context."""
        facts_str = ""
        if self.memory.facts:
            facts_str = "\n\nKnown facts about the user:\n" + \
                        "\n".join(f"- {k}: {v}" for k, v in self.memory.facts.items())

        # Switch personality for mentor mode
        base = self.MENTOR_PROMPT if self.mentor_active else CONFIG["personality"]
        system = base + facts_str
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
            # Show the real API error so the user knows what's wrong
            if "error" in data:
                err_msg = data["error"].get("message", str(data["error"]))
                err_type = data["error"].get("type", "")
                if "api_key" in err_msg.lower() or "auth" in err_type.lower():
                    return "Your API key isn't working sir. Please check it in the Anthropic console."
                if "credit" in err_msg.lower() or "billing" in err_msg.lower():
                    return "Looks like you're out of API credits sir. Add some at console.anthropic.com."
                return f"The AI returned an error: {err_msg}"
            reply = data["content"][0]["text"]
            self.memory.add_turn("assistant", reply)
            return reply
        except requests.exceptions.ConnectionError:
            return "I can't reach the internet right now sir. Check your connection."
        except requests.exceptions.Timeout:
            return "The AI took too long to respond sir. Try again."
        except KeyError as e:
            return f"Unexpected API response sir. Raw reply: {data}"
        except Exception as e:
            return f"Something went wrong sir: {e}"

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
        self.mentor_mode  = False  # toggled by "mentor mode" command

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
        if any(k in t for k in ["screenshot", "capture screen", "take a screenshot"]):
            return self._screenshot()

        if t.startswith("open "):
            return self._open_app(text[5:].strip())

        if t.startswith("close ") or t.startswith("quit ") or t.startswith("kill "):
            return self._close_app(text.split(" ", 1)[1].strip())

        # ── Mentor / conversation mode ────────────────────────────────────
        if any(k in t for k in [
            "mentor mode", "start mentor", "be my mentor", "talk to me",
            "help me think", "i need advice", "be my friend", "conversation mode"
        ]):
            return self._start_mentor_mode()

        if any(k in t for k in ["exit mentor", "stop mentor", "leave mentor", "end mentor"]):
            return self._stop_mentor_mode()

        # ── Voice to Notepad (dictation) ─────────────────────────────────
        if any(k in t for k in [
            "open notepad", "start notepad", "take notes", "write this down",
            "dictate", "start dictation", "voice note", "write a note",
            "note this", "type this"
        ]):
            return self._start_dictation()

        # ── System controls ──────────────────────────────────────────────
        if any(k in t for k in ["volume up", "increase volume", "louder", "turn up"]):
            return self._volume("up")

        if any(k in t for k in ["volume down", "decrease volume", "quieter", "turn down"]):
            return self._volume("down")

        if any(k in t for k in ["mute", "silence audio", "mute volume"]):
            return self._volume("mute")

        if any(k in t for k in ["unmute", "unmute volume", "turn sound on"]):
            return self._volume("unmute")

        if any(k in t for k in ["set volume"]):
            return self._volume_set(t)

        if any(k in t for k in ["brightness up", "increase brightness", "brighter", "screen brighter"]):
            return self._brightness("up")

        if any(k in t for k in ["brightness down", "decrease brightness", "dimmer", "screen dimmer"]):
            return self._brightness("down")

        if any(k in t for k in ["set brightness"]):
            return self._brightness_set(t)

        if any(k in t for k in ["shutdown computer", "shut down computer", "turn off computer",
                                  "shutdown laptop", "shut down laptop", "power off computer"]):
            return self._system_shutdown()

        if any(k in t for k in ["restart computer", "reboot", "restart laptop", "restart system"]):
            return self._system_restart()

        if any(k in t for k in ["lock screen", "lock my screen", "lock computer"]):
            return self._lock_screen()

        if any(k in t for k in ["sleep", "hibernate", "suspend", "put to sleep"]):
            return self._sleep()

        # ── App control ──────────────────────────────────────────────────
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

        if any(k in t for k in [
            "stop", "goodbye", "bye jarvis", "shut down", "shutdown",
            "exit", "quit jarvis", "turn off", "power off", "see you later",
            "that's all", "thats all", "i'm done", "close jarvis", "stop jarvis"
        ]):
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
        app_lower = app.lower().strip()

        # Common Windows app name → executable map
        WIN_APPS = {
            "notepad":       "notepad.exe",
            "calculator":    "calc.exe",
            "paint":         "mspaint.exe",
            "word":          "winword.exe",
            "excel":         "excel.exe",
            "powerpoint":    "powerpnt.exe",
            "outlook":       "outlook.exe",
            "file explorer": "explorer.exe",
            "explorer":      "explorer.exe",
            "task manager":  "taskmgr.exe",
            "control panel": "control.exe",
            "settings":      "ms-settings:",
            "camera":        "microsoft.windows.camera:",
            "calendar":      "outlookcal:",
            "maps":          "bingmaps:",
            "store":         "ms-windows-store:",
            "photos":        "ms-photos:",
            "snipping tool": "snippingtool.exe",
            "cmd":           "cmd.exe",
            "command prompt":"cmd.exe",
            "powershell":    "powershell.exe",
            "vs code":       "code.exe",
            "vscode":        "code.exe",
            "chrome":        "chrome.exe",
            "firefox":       "firefox.exe",
            "edge":          "msedge.exe",
            "vlc":           "vlc.exe",
            "zoom":          "zoom.exe",
            "teams":         "teams.exe",
            "discord":       "discord.exe",
            "steam":         "steam.exe",
            "spotify":       None,   # web fallback
            "gmail":         None,
            "youtube":       None,
            "whatsapp":      "whatsapp.exe",
        }
        WEB_APPS = {
            "spotify":  "https://open.spotify.com",
            "gmail":    "https://mail.google.com",
            "youtube":  "https://www.youtube.com",
            "notion":   "https://www.notion.so",
            "slack":    "https://app.slack.com",
            "maps":     "https://maps.google.com",
            "calendar": "https://calendar.google.com",
            "github":   "https://github.com",
            "chatgpt":  "https://chat.openai.com",
        }

        # Check web apps first
        for k, url in WEB_APPS.items():
            if k in app_lower:
                webbrowser.open(url)
                return f"Opening {app} in your browser."

        # Try Windows executable map
        exe = WIN_APPS.get(app_lower)
        if exe:
            try:
                if exe.endswith(":"):   # ms-settings: style URI
                    os.startfile(exe)
                else:
                    subprocess.Popen(exe, shell=True)
                return f"Opening {app}."
            except Exception as e:
                return f"Couldn't open {app}: {e}"

        # Generic fallback — try running the name directly
        try:
            if self.os_name == "Windows":
                subprocess.Popen(app, shell=True)
            elif self.os_name == "Darwin":
                subprocess.Popen(["open", "-a", app])
            elif self.os_name == "Linux":
                subprocess.Popen([app_lower])
            return f"Opening {app}."
        except Exception:
            return (f"I couldn't find {app} on your laptop. "
                    f"Make sure it's installed and try again.")

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

    # ── Mentor Mode ───────────────────────────────────────────────────────────
    def _start_mentor_mode(self) -> str:
        """Switch Jarvis into a warm, conversational friend/mentor persona."""
        self.mentor_mode = True
        self.ai.mentor_active = True
        return (
            "Mentor mode on. I'm here as your friend now. "
            "Talk to me about anything — share what's on your mind, ask me anything, "
            "and I'll help you think it through. What's going on?"
        )

    def _stop_mentor_mode(self) -> str:
        self.mentor_mode = False
        self.ai.mentor_active = False
        return "Back to assistant mode. Just say hey Jarvis whenever you need me."

    # ── Voice to Notepad (dictation) ──────────────────────────────────────────
    def _start_dictation(self) -> str:
        """
        Opens a dictation session — listens for voice, converts to text,
        appends to a .txt file, and opens it in Notepad when done.
        The user says 'stop dictation' or 'save and close' to finish.
        """
        ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        doc_path = Path.home() / "Documents" / f"jarvis_note_{ts}.txt"
        doc_path.parent.mkdir(exist_ok=True)

        speak(
            "Dictation mode started. Speak your text and I'll write it down. "
            "Say 'stop dictation' or 'save and close' when you're done.",
            self.wake
        )

        lines = []
        self.wake.pause()

        while True:
            chunk = listen_microphone(duration=8)
            if not chunk:
                speak("I didn't catch that — keep going or say stop dictation.", None)
                continue

            low = chunk.lower().strip()
            if any(k in low for k in ["stop dictation", "save and close", "finish note",
                                       "done dictating", "close notepad", "stop writing"]):
                break

            # Use Claude to clean up / punctuate the raw speech transcript
            cleaned = self._clean_dictation(chunk)
            lines.append(cleaned)
            speak(f"Got it.", None)

        self.wake.resume()

        if not lines:
            return "Nothing was dictated — no file created."

        content = "\n".join(lines)
        doc_path.write_text(content, encoding="utf-8")

        # Open in Notepad
        try:
            subprocess.Popen(["notepad.exe", str(doc_path)])
        except Exception:
            pass

        return (
            f"Done! I've written {len(lines)} paragraph{'s' if len(lines)>1 else ''} "
            f"and saved your note as {doc_path.name}. Opening it in Notepad now."
        )

    def _clean_dictation(self, raw: str) -> str:
        """Ask Claude to add punctuation and capitalisation to raw spoken text."""
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.ai.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 300,
                    "system": (
                        "You are a transcription assistant. "
                        "The user has spoken text captured by voice recognition. "
                        "Add proper punctuation, capitalisation, and paragraph breaks. "
                        "Fix obvious speech-to-text errors. "
                        "Return ONLY the cleaned text — nothing else."
                    ),
                    "messages": [{"role": "user", "content": raw}],
                },
                timeout=10,
            )
            return resp.json()["content"][0]["text"].strip()
        except Exception:
            return raw  # fallback: return raw if Claude unreachable

    # ── Volume controls (Windows-native, no third-party tools needed) ─────────
    def _volume(self, direction: str) -> str:
        try:
            if self.os_name == "Windows":
                # Use PowerShell + Windows Audio COM — no nircmd.exe needed
                scripts = {
                    "up":     "(New-Object -ComObject WScript.Shell).SendKeys([char]175); "
                              "(New-Object -ComObject WScript.Shell).SendKeys([char]175)",
                    "down":   "(New-Object -ComObject WScript.Shell).SendKeys([char]174); "
                              "(New-Object -ComObject WScript.Shell).SendKeys([char]174)",
                    "mute":   "(New-Object -ComObject WScript.Shell).SendKeys([char]173)",
                    "unmute": "(New-Object -ComObject WScript.Shell).SendKeys([char]173)",
                }
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", scripts[direction]],
                    check=False, timeout=5
                )
            elif self.os_name == "Darwin":
                cmds = {
                    "up":   "set volume output volume (output volume of (get volume settings) + 10)",
                    "down": "set volume output volume (output volume of (get volume settings) - 10)",
                    "mute": "set volume with output muted",
                    "unmute": "set volume without output muted",
                }
                subprocess.run(["osascript", "-e", cmds[direction]])
            elif self.os_name == "Linux":
                cmds = {"up": "5%+", "down": "5%-", "mute": "toggle", "unmute": "unmute"}
                subprocess.run(["amixer", "-q", "sset", "Master", cmds[direction]])

            msgs = {
                "up": "Volume up.", "down": "Volume down.",
                "mute": "Muted.", "unmute": "Unmuted."
            }
            return msgs.get(direction, "Done.")
        except Exception as e:
            return f"Volume control failed: {e}"

    def _volume_set(self, text: str) -> str:
        """Set volume to a specific percentage — 'set volume to 50'."""
        import re
        m = re.search(r"(\d+)", text)
        if not m:
            return "Please say a number, like 'set volume to 50'."
        level = max(0, min(100, int(m.group(1))))
        try:
            if self.os_name == "Windows":
                # Use PowerShell to set exact volume level via Windows Audio API
                script = (
                    f"$volume = {level / 100.0}; "
                    f"Add-Type -TypeDefinition '"
                    f"using System.Runtime.InteropServices; "
                    f"public class Vol {{ "
                    f"  [DllImport(\"winmm.dll\")] "
                    f"  public static extern int waveOutSetVolume(IntPtr h, uint vol); "
                    f"}}'; "
                    f"$v = [uint32]([Math]::Round($volume * 65535)); "
                    f"$combined = ($v -shl 16) -bor $v; "
                    f"[Vol]::waveOutSetVolume([IntPtr]::Zero, $combined) | Out-Null"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", script],
                    check=False, timeout=8
                )
            return f"Volume set to {level} percent."
        except Exception:
            return f"Tried to set volume to {level}%. Use your keyboard if it didn't work."

    # ── Brightness controls ───────────────────────────────────────────────────
    def _brightness(self, direction: str) -> str:
        try:
            if self.os_name == "Windows":
                # Read current brightness then adjust
                ps_get = (
                    "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness)"
                    ".CurrentBrightness"
                )
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_get],
                    capture_output=True, text=True, timeout=5
                )
                current = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 50
                step = 10
                new_level = max(0, min(100, current + step if direction == "up" else current - step))
                ps_set = (
                    f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                    f".WmiSetBrightness(1, {new_level})"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_set],
                    check=False, timeout=5
                )
                return f"Brightness {'increased' if direction == 'up' else 'decreased'} to {new_level}%."
            elif self.os_name == "Darwin":
                val = "0.8" if direction == "up" else "0.4"
                subprocess.run(["brightness", val], check=False)
                return f"Brightness {'increased' if direction == 'up' else 'decreased'}."
            elif self.os_name == "Linux":
                subprocess.run(["xbacklight", f"-{direction == 'up' and 'inc' or 'dec'}", "10"])
                return f"Brightness {'increased' if direction == 'up' else 'decreased'}."
        except Exception as e:
            return f"Brightness control failed: {e}"

    def _brightness_set(self, text: str) -> str:
        import re
        m = re.search(r"(\d+)", text)
        if not m:
            return "Please say a number, like 'set brightness to 70'."
        level = max(0, min(100, int(m.group(1))))
        try:
            if self.os_name == "Windows":
                ps = (
                    f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                    f".WmiSetBrightness(1, {level})"
                )
                subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               check=False, timeout=5)
            return f"Brightness set to {level}%."
        except Exception as e:
            return f"Couldn't set brightness: {e}"

    # ── Shutdown & Restart ────────────────────────────────────────────────────
    def _system_shutdown(self) -> str:
        speak(
            "Alright sir, shutting down your computer in 10 seconds. "
            "Make sure you've saved everything.",
            self.wake
        )
        time.sleep(2)
        try:
            if self.os_name == "Windows":
                subprocess.run(["shutdown", "/s", "/t", "10"], check=False)
            elif self.os_name == "Darwin":
                subprocess.run(["sudo", "shutdown", "-h", "+1"], check=False)
            elif self.os_name == "Linux":
                subprocess.run(["shutdown", "-h", "+1"], check=False)
            return "Shutdown initiated. Goodbye sir!"
        except Exception as e:
            return f"Shutdown failed: {e}"

    def _system_restart(self) -> str:
        speak(
            "Restarting your computer in 10 seconds sir. "
            "Save your work now.",
            self.wake
        )
        time.sleep(2)
        try:
            if self.os_name == "Windows":
                subprocess.run(["shutdown", "/r", "/t", "10"], check=False)
            elif self.os_name == "Darwin":
                subprocess.run(["sudo", "shutdown", "-r", "+1"], check=False)
            elif self.os_name == "Linux":
                subprocess.run(["shutdown", "-r", "+1"], check=False)
            return "Restart initiated."
        except Exception as e:
            return f"Restart failed: {e}"

    def _help(self) -> str:
        mentor_status = "active" if self.mentor_mode else "off"
        return (
            "Here's what I can do. "
            "For apps: say 'open notepad', 'open chrome', 'open calculator', or any app name. "
            "For volume: 'volume up', 'volume down', 'mute', 'set volume to 50'. "
            "For brightness: 'brightness up', 'brightness down', 'set brightness to 70'. "
            "For system: 'shutdown computer', 'restart computer', 'lock screen', 'sleep'. "
            "For notes: say 'take notes' or 'start dictation' and I'll write what you say into a file. "
            f"For mentor mode (currently {mentor_status}): say 'mentor mode' and I'll be your friend and advisor. "
            "And of course I can answer any question, search the web, check the weather, and generate images. "
            "What would you like to do?"
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

    # ── Test TTS immediately so we know if voice output works ────────────
    print("\n🔊 Testing voice output...")
    _init_tts()
    if _tts_mode == "silent":
        print("⚠️  WARNING: No working text-to-speech found.")
        print("   Jarvis will type responses but NOT speak them.")
        print("   Fix: pip uninstall pyttsx3 && pip install pyttsx3")
        print("   Or check that your speaker/headphones are connected and not muted.\n")
    else:
        print(f"✅ Voice output working — using {_tts_mode}\n")

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
                    speak(
                        "Hello sir, I'm Jarvis, your personal assistant at work. "
                        "How may I help you?",
                        None
                    )
                    user_input = listen_microphone()
                    wake.resume()
                    if not user_input:
                        speak("I didn't catch that. Say hey Jarvis to try again.", wake)
                        continue
                    # Acknowledge input was captured before processing
                    speak("I got you.", wake)
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
                import random
                goodbyes = [
                    "Goodbye sir, take care!",
                    "See you later sir. Shutting down now.",
                    "Alright, signing off. Goodbye!",
                    "Take care sir. I'll be here when you need me.",
                    "Goodbye! It was good talking with you."
                ]
                speak(random.choice(goodbyes), wake)
                time.sleep(1)
                wake.stop()
                memory.save()
                break

            if response:
                speak(response, wake)

            # ── Mentor mode: keep talking without wake word ───────────────
            while handler.mentor_mode and use_voice:
                mentor_prompt = listen_microphone()
                if not mentor_prompt:
                    speak("I'm still here — go on.", wake)
                    continue
                low = mentor_prompt.lower().strip()
                if any(k in low for k in ["exit mentor", "stop mentor", "leave mentor",
                                           "end mentor", "goodbye", "bye"]):
                    reply = handler._stop_mentor_mode()
                    speak(reply, wake)
                    break
                reply = handler.handle(mentor_prompt)
                if reply and reply != "SHUTDOWN":
                    speak(reply, wake)

        except KeyboardInterrupt:
            speak("Alright, shutting down. Goodbye!", wake)
            wake.stop()
            memory.save()
            break


if __name__ == "__main__":
    main()
