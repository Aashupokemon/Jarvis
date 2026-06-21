"""
JARVIS — Phase 4: Screen Vision

Lets Jarvis "see" your screen by taking a screenshot and sending it to
Claude's vision capability. Useful for:
  - "What's on my screen?"
  - "What does this error mean?"
  - "Summarize this webpage"
  - "What app is this?"

Requires: pyautogui, pillow
"""

import base64
import io
import datetime
from pathlib import Path

import requests


class ScreenVision:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def capture_screenshot(self) -> bytes | None:
        """Take a screenshot and return PNG bytes."""
        try:
            import pyautogui
            img = pyautogui.screenshot()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except ImportError:
            return None
        except Exception as e:
            print(f"[Vision] Screenshot failed: {e}")
            return None

    def capture_region(self, x: int, y: int, width: int, height: int) -> bytes | None:
        """Capture a specific region of the screen."""
        try:
            import pyautogui
            img = pyautogui.screenshot(region=(x, y, width, height))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            print(f"[Vision] Region capture failed: {e}")
            return None

    def ask_about_screen(self, question: str = "What's on my screen? Describe it briefly.") -> str:
        """Take a screenshot and ask Claude about it."""
        screenshot_bytes = self.capture_screenshot()
        if not screenshot_bytes:
            return "I couldn't capture your screen. Make sure pyautogui is installed."

        b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")

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
                    "max_tokens": 400,
                    "system": "You are Jarvis, analyzing the user's screen. Be concise (2-4 sentences) "
                             "and conversational, as if briefing them verbally. Don't describe every "
                             "pixel — focus on what's relevant to their question.",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": b64_image,
                                    },
                                },
                                {"type": "text", "text": question},
                            ],
                        }
                    ],
                },
                timeout=30,
            )
            data = response.json()
            if "content" in data:
                return data["content"][0]["text"]
            return f"Vision request failed: {data.get('error', {}).get('message', 'unknown error')}"
        except Exception as e:
            return f"Couldn't analyze the screen: {e}"

    def save_annotated_screenshot(self) -> str:
        """Save a screenshot with timestamp for reference."""
        screenshot_bytes = self.capture_screenshot()
        if not screenshot_bytes:
            return "Couldn't capture screen."
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path.home() / "Pictures" / f"jarvis_vision_{ts}.png"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(screenshot_bytes)
        return str(path)


# ─── Command routing helper ───────────────────────────────────────────────
def route_vision_command(text: str, vision: ScreenVision) -> str | None:
    """
    Call this from CommandHandler.handle() before the AI fallback.
    Returns None if the text isn't a vision-related command.
    """
    t = text.lower().strip()

    vision_triggers = [
        "what's on my screen", "what is on my screen", "describe my screen",
        "what do you see", "look at my screen", "what's this", "what is this on screen",
        "read my screen", "what does this say", "explain this error",
        "summarize this page", "what app is this", "what am i looking at"
    ]

    if any(k in t for k in vision_triggers):
        question = text if len(text) > 20 else "What's on my screen? Describe it briefly."
        return vision.ask_about_screen(question)

    return None


# ─────────────────────────────────────────────────────────────────────────
# INTEGRATION SNIPPET — add to jarvis.py's CommandHandler:
#
#   from screen_vision import ScreenVision, route_vision_command
#   # in __init__: self.vision = ScreenVision(jarvis_ai.api_key)
#   # in handle(), before the AI fallback:
#   vision_result = route_vision_command(text, self.vision)
#   if vision_result:
#       return vision_result
# ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        v = ScreenVision(api_key)
        print(v.ask_about_screen())
    else:
        print("Set ANTHROPIC_API_KEY to test.")
