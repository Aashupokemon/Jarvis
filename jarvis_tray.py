"""
JARVIS — Phase 4: System Tray GUI

A lightweight tray icon + status window so Jarvis runs quietly in the
background instead of needing a terminal window open all the time.

Run this INSTEAD of jarvis.py directly when you want the tray experience.
It imports and drives the core engine from jarvis.py.

Tray menu:
  - Show/Hide console
  - Toggle voice mode
  - Toggle wake word listening
  - View memory summary
  - Reload skills
  - Quit
"""

import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import jarvis as core  # the Phase 3 engine


class JarvisTrayApp:
    def __init__(self):
        self.memory  = core.Memory()
        self.skills  = core.SkillsManager()
        self.plugins = core.PluginManager()

        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("Set ANTHROPIC_API_KEY environment variable before launching the tray app.")
            sys.exit(1)

        self.ai = core.JarvisAI(api_key, self.memory)
        self.voice_available = core.load_whisper_model()

        self.wake = core.WakeWordDetector(self._on_wake, core.CONFIG)
        self.handler = core.CommandHandler(self.ai, self.memory, self.skills,
                                            self.plugins, self.wake)

        self._listening_active = False
        self._icon = None
        self._status = "Idle"

    # ── Wake word callback ───────────────────────────────────────────────
    def _on_wake(self):
        self._status = "Listening..."
        self._update_icon_title()
        core.speak("Yes?", None)
        text = core.listen_microphone()
        if text:
            self._process(text)
        else:
            core.speak("I didn't catch that.", self.wake)
        self._status = "Idle"
        self._update_icon_title()

    def _process(self, text: str):
        self._status = f"Processing: {text[:30]}"
        self._update_icon_title()
        response = self.handler.handle(text)
        if response == "SHUTDOWN":
            self.quit(None, None)
            return
        if response:
            core.speak(response, self.wake)

    def _update_icon_title(self):
        if self._icon:
            self._icon.title = f"Jarvis — {self._status}"

    # ── Tray menu actions ────────────────────────────────────────────────
    def toggle_listening(self, icon, item):
        if self._listening_active:
            self.wake.stop()
            self._listening_active = False
            self._status = "Wake word off"
        else:
            if self.voice_available:
                self.wake.start()
                self._listening_active = True
                self._status = "Listening for wake word"
            else:
                self._status = "Voice unavailable (install whisper)"
        self._update_icon_title()

    def speak_test(self, icon, item):
        core.speak("Jarvis tray is online and ready, sir.", self.wake)

    def show_memory(self, icon, item):
        summary = self.memory.summarize()
        core.speak(summary, self.wake)

    def reload_skills(self, icon, item):
        msg = self.skills.reload()
        core.speak(msg, self.wake)

    def type_command(self, icon, item):
        """Open a simple input prompt via terminal fallback (tray has no text box)."""
        def ask():
            try:
                text = input("⌨️  Jarvis (tray) > ").strip()
                if text:
                    self._process(text)
            except Exception:
                pass
        threading.Thread(target=ask, daemon=True).start()

    def quit(self, icon, item):
        self.wake.stop()
        self.memory.save()
        if self._icon:
            self._icon.stop()
        sys.exit(0)

    # ── Icon image ───────────────────────────────────────────────────────
    def _make_icon_image(self):
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Simple circular "J" badge
        draw.ellipse((4, 4, 60, 60), fill=(30, 144, 200, 255))
        draw.text((24, 18), "J", fill=(255, 255, 255, 255))
        return img

    # ── Run ──────────────────────────────────────────────────────────────
    def run(self):
        import pystray
        from pystray import MenuItem as Item, Menu

        menu = Menu(
            Item("Speak test", self.speak_test),
            Item("Type a command...", self.type_command),
            Item("Toggle wake-word listening", self.toggle_listening,
                 checked=lambda item: self._listening_active),
            Item("Show memory summary", self.show_memory),
            Item("Reload skills", self.reload_skills),
            Item("Quit Jarvis", self.quit),
        )

        self._icon = pystray.Icon("jarvis", self._make_icon_image(), "Jarvis — Idle", menu)

        # Auto-start wake word listening if voice is available
        if self.voice_available:
            self.wake.start()
            self._listening_active = True
            self._status = "Listening for wake word"

        core.speak(f"Jarvis tray active. {self.memory.summarize()}", self.wake)

        self._icon.run()


def main():
    print("""
╔══════════════════════════════════════════════╗
║   J.A.R.V.I.S  —  Tray Mode (Phase 4)       ║
║   Runs quietly in your system tray          ║
╚══════════════════════════════════════════════╝

Right-click the tray icon for options.
Console stays open for typed commands and logs.
""")
    app = JarvisTrayApp()
    app.run()


if __name__ == "__main__":
    main()
